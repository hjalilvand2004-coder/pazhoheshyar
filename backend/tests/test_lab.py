"""تست‌های آزمایشگاه شبیه‌سازی پژوهش — دیتاست، کاوش، همبستگی، مدل‌ها، پیش‌بینی و اتصال به سند"""
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def login(client, username, password="12345678"):
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def tokens(client):
    return {"prof": login(client, "prof1"), "stu": login(client, "student1"),
            "stu2": login(client, "student2"), "mgr": login(client, "manager1")}


# ---------- ساخت دیتاست قطعی (توزیع‌های شناخته‌شده برای سنجش درستی مدل‌ها) ----------

def _make_csv():
    import random
    rng = random.Random(7)
    lines = ["hours_study,attendance,sleep,gender,grade,pass_fail"]
    for i in range(150):
        group = i % 3          # سه گروه برای خوشه‌بندی و ANOVA
        hours = round(2 + group * 2 + rng.uniform(-1, 1), 2)
        attendance = round(55 + group * 10 + rng.uniform(-6, 6), 1)
        sleep = round(6 + rng.uniform(-1.5, 1.5), 1)
        gender = "زن" if i % 2 else "مرد"
        grade = round(10 + 2.2 * hours + 0.08 * attendance + rng.uniform(-2, 2), 2)
        pf = "قبول" if grade >= 18 else "مردود"
        lines.append(f"{hours},{attendance},{sleep},{gender},{grade},{pf}")
    return "\n".join(lines).encode("utf-8")


def _upload(client, h, content=None, title="داده آموزشی نمونه", filename="students.csv"):
    content = content or _make_csv()
    r = client.post("/api/v1/lab/datasets", headers=h,
                    files={"file": (filename, content, "text/csv")},
                    data={"title": title})
    assert r.status_code == 200, r.text
    return r.json()


def _run_exp(client, h, ds_id, task, model, target="", features=None, params=None):
    body = {"dataset_id": ds_id, "task": task, "model": model,
            "target": target, "features": features or [], "params": params or {}}
    return client.post("/api/v1/lab/experiments", headers=h, json=body)


def test_meta_and_services_registry(client):
    r = client.get("/api/v1/lab/meta")
    assert r.status_code == 200
    tasks = {t["key"]: t for t in r.json()["tasks"]}
    assert {"regression", "classification", "clustering"} <= set(tasks)
    assert any(m["key"] == "forest" for m in tasks["regression"]["models"])
    r = client.get("/api/v1/services")
    mods = {s["module"]: s for s in r.json()["services"]}
    assert "lab" in mods and any("attach-doc" in e for e in mods["lab"]["endpoints"])


def test_upload_csv_and_profile(client, tokens):
    h = auth(tokens["prof"])
    d = _upload(client, h)
    assert d["n_rows"] == 150 and d["n_cols"] == 6
    dt = {c["name"]: c["dtype"] for c in d["columns_meta"]}
    assert dt["hours_study"] == "numeric" and dt["gender"] == "categorical" and dt["pass_fail"] == "categorical"
    # پیش‌نمایش و جزئیات
    det = client.get(f"/api/v1/lab/datasets/{d['id']}", headers=h).json()
    assert len(det["preview"]) == 20 and det["preview"][0]["hours_study"] is not None
    # پروفایل توصیفی
    p = client.get(f"/api/v1/lab/datasets/{d['id']}/profile", headers=h).json()
    cols = {c["name"]: c for c in p["columns"]}
    assert cols["hours_study"]["count"] == 150 and cols["hours_study"]["hist"]["counts"]
    assert cols["grade"]["mean"] > 10 and cols["grade"]["outliers"] is not None
    assert cols["gender"]["top"][0]["count"] == 75
    assert p["missing_cells"] == 0
    # فایل نامعتبر رد می‌شود
    r = client.post("/api/v1/lab/datasets", headers=h,
                    files={"file": ("x.csv", b"only,one,line", "text/csv")}, data={"title": "بد"})
    assert r.status_code == 400


def test_upload_xlsx_and_persian_digits(client, tokens):
    h = auth(tokens["stu"])
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["سن", "شهر", "مصرف"])
    for i in range(40):
        ws.append([f"۲{i}", "تهران" if i % 2 else "اصفهان", 100 + i])
    buf = io.BytesIO()
    wb.save(buf)
    d = _upload(client, h, buf.getvalue(), "رفتار مصرف", filename="students.xlsx")
    dt = {c["name"]: c["dtype"] for c in d["columns_meta"]}
    assert dt["مصرف"] == "numeric" and dt["شهر"] == "categorical"
    assert d["n_rows"] == 40


def test_correlations_scatter_crosstab_anova(client, tokens):
    h = auth(tokens["prof"])
    ds = _upload(client, h)
    # همبستگی قوی ساعت مطالعه با نمره
    r = client.get(f"/api/v1/lab/datasets/{ds['id']}/correlations", headers=h)
    body = r.json()
    assert r.status_code == 200 and len(body["columns"]) == 4
    pairs = {tuple(sorted((s["a"], s["b"]))): s["r"] for s in body["strong_pairs"]}
    key = tuple(sorted(("hours_study", "grade")))
    assert key in pairs and abs(pairs[key]) > 0.7
    r = client.get(f"/api/v1/lab/datasets/{ds['id']}/correlations?method=spearman", headers=h)
    assert r.status_code == 200
    r = client.get(f"/api/v1/lab/datasets/{ds['id']}/correlations?method=bad", headers=h)
    assert r.status_code == 400
    # پراکندگی با روند
    r = client.get(f"/api/v1/lab/datasets/{ds['id']}/scatter?x=hours_study&y=grade&hue=gender", headers=h)
    sc = r.json()
    assert sc["n_valid"] == 150 and len(sc["points"]) == 150 and len(sc["groups"]) == 2
    assert abs(sc["trend"]["r"]) > 0.7
    # کای‌دوی جنسیت و قبولی (مستقل ساخته شده)
    r = client.get(f"/api/v1/lab/datasets/{ds['id']}/crosstab?a=gender&b=pass_fail", headers=h)
    ct = r.json()
    assert r.status_code == 200 and ct["chi2"] is not None and ct["p_value"] is not None
    # ANOVA نمره بر حسب گروه‌های رفتاری — سه گروه با میانگین‌های متفاوت
    r = client.get(f"/api/v1/lab/datasets/{ds['id']}/anova?target=grade&group=pass_fail", headers=h)
    av = r.json()
    assert r.status_code == 200 and len(av["groups"]) == 2 and av["p_value"] is not None


def test_access_control_on_dataset(client, tokens):
    h_p, h_s2 = auth(tokens["prof"]), auth(tokens["stu2"])
    ds = _upload(client, h_p)
    assert client.get(f"/api/v1/lab/datasets/{ds['id']}", headers=h_s2).status_code == 403
    assert client.get(f"/api/v1/lab/datasets/{ds['id']}/profile", headers=h_s2).status_code == 403
    r = _run_exp(client, h_s2, ds["id"], "regression", "linear", target="grade",
                 features=["hours_study", "attendance"])
    assert r.status_code == 403
    # مدیر پژوهش دسترسی مشاهده دارد
    assert client.get(f"/api/v1/lab/datasets/{ds['id']}", headers=auth(tokens["mgr"])).status_code == 200
    assert client.get("/api/v1/lab/datasets/all", headers=auth(tokens["stu2"])).status_code == 403


def test_regression_experiment_and_predict(client, tokens):
    h = auth(tokens["prof"])
    ds = _upload(client, h)
    r = _run_exp(client, h, ds["id"], "regression", "linear", target="grade",
                 features=["hours_study", "attendance", "sleep", "gender"])
    assert r.status_code == 200, r.text
    e = r.json()
    assert e["status"] == "completed"
    m = e["metrics"]
    # رابطهٔ خطی قوی تزریقی شده است — مدل باید آن را بازیابی کند
    assert m["r2_test"] > 0.8, m
    assert m["rmse_test"] < 2 and m["n_train"] + m["n_test"] == 150
    arts = e["artifacts"]
    assert arts["pred_actual"] and arts["residual_hist"]["counts"]
    coefs = {c["feature"]: c["value"] for c in arts["coefficients"]}
    assert coefs.get("hours_study", 0) > 1.5       # ضرایب تزریقی بازیابی شده‌اند
    assert any("gender=" in f for f in coefs)       # کدگذاری مقوله‌ای اعمال شده
    # مقایسه با جنگل تصادفی در فهرست آزمایش‌ها
    r = _run_exp(client, h, ds["id"], "regression", "forest", target="grade",
                 features=["hours_study", "attendance", "sleep", "gender"])
    assert r.status_code == 200 and r.json()["metrics"]["r2_test"] > 0.6
    lst = client.get("/api/v1/lab/experiments", headers=h).json()
    assert len(lst) == 2 and all("artifacts" not in x for x in lst)
    # پیش‌بینی تک‌ردیفی — ساعت مطالعه بالا نمرهٔ بالاتر می‌دهد
    p1 = client.post(f"/api/v1/lab/experiments/{e['id']}/predict", headers=h,
                     json={"row": {"hours_study": 8, "attendance": 92, "sleep": 7, "gender": "مرد"}}).json()
    p2 = client.post(f"/api/v1/lab/experiments/{e['id']}/predict", headers=h,
                     json={"row": {"hours_study": 1, "attendance": 55, "sleep": 7, "gender": "مرد"}}).json()
    assert p1["prediction"] > p2["prediction"]
    # مقدار گمشده در پیش‌بینی با میانگین آموزش جای‌گذاری می‌شود (خطا نمی‌دهد)
    p3 = client.post(f"/api/v1/lab/experiments/{e['id']}/predict", headers=h,
                     json={"row": {"hours_study": None, "attendance": 70, "gender": "زن"}}).json()
    assert isinstance(p3["prediction"], float)
    # حذف آزمایش
    eid = client.get("/api/v1/lab/experiments", headers=h).json()[0]["id"]
    assert client.delete(f"/api/v1/lab/experiments/{eid}", headers=h).json()["ok"] is True


def test_regression_validation_errors(client, tokens):
    h = auth(tokens["prof"])
    ds = _upload(client, h)
    r = _run_exp(client, h, ds["id"], "regression", "linear", target="gender",
                 features=["hours_study"])
    assert r.status_code == 400          # هدف رگرسیون باید عددی باشد
    r = _run_exp(client, h, ds["id"], "regression", "linear", target="grade", features=["grade"])
    assert r.status_code == 400          # هدف نمی‌تواند ویژگی باشد
    r = _run_exp(client, h, ds["id"], "classification", "kmeans", target="pass_fail",
                 features=["hours_study"])
    assert r.status_code == 400          # مدل با وظیفه ناسازگار


def test_classification_experiment(client, tokens):
    h = auth(tokens["prof"])
    ds = _upload(client, h)
    r = _run_exp(client, h, ds["id"], "classification", "logistic", target="pass_fail",
                 features=["hours_study", "attendance", "sleep", "gender"])
    assert r.status_code == 200, r.text
    e = r.json()
    m = e["metrics"]
    assert m["accuracy_test"] > 0.8, m
    assert sorted(m["classes"]) == ["قبول", "مردود"]
    arts = e["artifacts"]
    assert len(arts["confusion"]["matrix"]) == 2 and sum(
        sum(row) for row in arts["confusion"]["matrix"]) == m["n_test"]
    assert arts["per_class"][0]["label"] in ("قبول", "مردود")
    assert arts["roc"]["auc"] > 0.8 and len(arts["roc"]["points"]) >= 4
    assert arts["coefficients"] and any("hours_study" == c["feature"] for c in arts["coefficients"])
    # پیش‌بینی با احتمال‌ها
    p = client.post(f"/api/v1/lab/experiments/{e['id']}/predict", headers=h,
                    json={"row": {"hours_study": 9, "attendance": 95, "sleep": 7, "gender": "زن"}}).json()
    assert p["prediction"] in ("قبول", "مردود") and "probabilities" in p
    assert abs(sum(p["probabilities"].values()) - 1.0) < 0.01


def test_clustering_experiment(client, tokens):
    h = auth(tokens["prof"])
    ds = _upload(client, h)
    r = _run_exp(client, h, ds["id"], "clustering", "kmeans",
                 features=["hours_study", "attendance"], params={"scaled": True})
    assert r.status_code == 200, r.text
    e = r.json()
    m = e["metrics"]
    # سه گروه رفتاری تزریقی شده — K-Means باید حدود سه خوشه پیدا کند
    assert m["n_clusters"] == 3, m
    assert m["silhouette"] > 0.3, m
    assert sum(m["cluster_sizes"].values()) == 150
    assert m["elbow"] and len(m["elbow"]) == 8 and m["k_chosen"] == 3
    arts = e["artifacts"]
    assert len(arts["pca_scatter"]) == 150 and len(arts["cluster_profile"]) == 3
    prof = {p["cluster"]: p["means"] for p in arts["cluster_profile"]}
    means_sorted = sorted((p["means"]["hours_study"] for p in arts["cluster_profile"]))
    assert means_sorted[-1] - means_sorted[0] > 3   # تفکیک رفتاری قابل مشاهده
    assert arts["pca_centroids"] and arts["pca_variance"]
    # پیش‌بینی خوشه
    p = client.post(f"/api/v1/lab/experiments/{e['id']}/predict", headers=h,
                    json={"row": {"hours_study": 8, "attendance": 92}}).json()
    assert p["prediction"] in (0, 1, 2)
    # خوشه‌بندی با ویژگی مقوله‌ای رد می‌شود
    r = _run_exp(client, h, ds["id"], "clustering", "kmeans",
                 features=["hours_study", "gender"])
    assert r.status_code == 400


def test_attach_experiment_results_to_research_doc(client, tokens):
    h_p, h_s = auth(tokens["prof"]), auth(tokens["stu"])
    ds = _upload(client, h_p)
    e = _run_exp(client, h_p, ds["id"], "regression", "linear", target="grade",
                 features=["hours_study", "attendance", "sleep", "gender"]).json()
    # سند پژوهشی توسط استاد؛ دانشجو نویسنده می‌شود
    d = client.post("/api/v1/research/docs", headers=h_p,
                    json={"title": "پیش‌بینی عملکرد تحصیلی", "template": "fa-thesis", "language": "fa"}).json()
    client.post(f"/api/v1/research/docs/{d['id']}/members", headers=h_p,
                json={"username": "student1", "role": "writer"})
    # دانشجوی بیگانه حق درج ندارد
    r = client.post(f"/api/v1/lab/experiments/{e['id']}/attach-doc", headers=auth(tokens["stu2"]),
                    json={"doc_id": d["id"]})
    assert r.status_code == 403
    # نویسندهٔ سند که سازندهٔ آزمایش نیست هم حق درج ندارد (سیاست: سازندهٔ آزمایش)
    r = client.post(f"/api/v1/lab/experiments/{e['id']}/attach-doc", headers=h_s,
                    json={"doc_id": d["id"]})
    assert r.status_code == 403
    # درج خودکار در بخش «یافته‌های پژوهش» توسط سازندهٔ آزمایش (مسئول سند)
    r = client.post(f"/api/v1/lab/experiments/{e['id']}/attach-doc", headers=h_p,
                    json={"doc_id": d["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["section_heading"] == "یافته‌های پژوهش"
    det = client.get(f"/api/v1/research/docs/{d['id']}", headers=h_p).json()
    sec = next(s for s in det["sections"] if s["heading"] == "یافته‌های پژوهش")
    assert "نتایج شبیه‌سازی" in sec["body"] and "R²" in sec["body"] and e["model_fa"] in sec["body"]
    # درج در بخش مشخص‌شده
    other = det["sections"][1]
    r = client.post(f"/api/v1/lab/experiments/{e['id']}/attach-doc", headers=h_p,
                    json={"doc_id": d["id"], "section_id": other["id"]})
    assert r.status_code == 200 and r.json()["section_id"] == other["id"]
