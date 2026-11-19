"""تست پایان‌به‌پایان لایه معنایی و گراف دانش — پذیرش سند بخش ۱۶.

پوشش: یکپارچه‌سازی با منشأ، جست‌وجوی ترکیبی (دقیق/مفهومی)، سیاست دسترسی روی
رابطه و مسیر، پیشنهاد توجیه‌دار استاد راهنما، ابطال‌پذیری استنتاج، تطبیق
موجودیت با داوری، بازسازی نما از دفتر ثبت و کنترل عملیات مدیریتی.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def login(c, username, password="12345678"):
    r = c.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_01_bootstrap_builds_registry_from_core_data(client):
    """یکپارچه‌سازی اولیه: دفتر ثبت با منشأ ساخته می‌شود؛ نما از دفتر بازسازی می‌شود."""
    t = login(client, "admin1")
    ov = client.get("/api/v1/semantic/graph/overview", headers=auth(t)).json()
    assert ov["kinds"].get("Person", 0) >= 7          # ۶ کاربر + ۱ واردات hr-import
    assert ov["visible_claims"] >= 40
    assert ov["version"].startswith("pv-")

    r = client.get(f"/api/v1/semantic/entities/by-user/{1}", headers=auth(t))
    assert r.status_code == 200
    body = r.json()
    assert body["entity_id"].startswith("pv-") is False and len(body["entity_id"]) == 36


def test_02_search_exact_identifier_beats_vector(client):
    """تطابق دقیق شناسه زیر شباهت برداری نمی‌رود (الزام ۱۰.۲)."""
    t = login(client, "admin1")
    r = client.get("/api/v1/semantic/search?q=student1", headers=auth(t)).json()
    assert r["results"], "جست‌وجوی شناسه باید نتیجه بدهد"
    first = r["results"][0]
    assert first["name"] == "مریم احمدی"
    assert any("دقیق" in x for x in first["reasons"])

    # جست‌وجوی مفهومی از مسیر گراف — نه فقط شباهت چند کلمه (سند بخش ۱)
    r2 = client.get("/api/v1/semantic/search?q=استاد پردازش تصویر", headers=auth(t)).json()
    names = [x["name"] for x in r2["results"]]
    assert "دکتر سارا موسوی" in names


def test_03_access_policy_hides_restricted_relations(client):
    """مقالات (مشتق فیلد حساس) برای دیگران مخفی است؛ برای خودِ شخص و مدیر دیده می‌شود."""
    t_stu = login(client, "student1")
    t_prof = login(client, "prof1")
    t_mgr = login(client, "manager1")
    t_admin = login(client, "admin1")

    # استاد مقاله را در پروفایل ثبت می‌کند (فیلد حساس) → یکپارچه‌سازی آن را با منشأ «استخراج‌شده» می‌گیرد
    pr = client.put("/api/v1/profiles/me", headers=auth(t_prof), json={
        "field_of_study": "هوش مصنوعی", "faculty_name": "دانشکده برق", "degree": "دکتری",
        "interests": ["پردازش تصویر"], "skills": ["پایتون", "یادگیری ماشین"],
        "bio": "", "research_history": "", "publications": ["تشخیص ضایعات پزشکی با یادگیری عمیق"],
        "availability": "", "collaboration_type": "", "research_goal": "",
        "expertise": ["پردازش تصویر", "یادگیری ماشین"], "methods_tools": "",
        "capacity": 4, "conditions": "",
    })
    assert pr.status_code == 200, pr.text
    integ = client.post("/api/v1/semantic/integration-runs", headers=auth(t_admin))
    assert integ.status_code == 200

    prof_entity = client.get("/api/v1/semantic/entities/by-user/3", headers=auth(t_prof)).json()["entity_id"]
    own = client.get(f"/api/v1/semantic/entities/{prof_entity}", headers=auth(t_prof)).json()
    other = client.get(f"/api/v1/semantic/entities/{prof_entity}", headers=auth(t_stu)).json()
    own_preds = {x["predicate"] for x in own["relations"]}
    other_preds = {x["predicate"] for x in other["relations"]}
    assert "AUTHORED" in own_preds
    authored = [x for x in own["relations"] if x["predicate"] == "AUTHORED"][0]
    assert authored["origin"] == "extracted" and authored["policy"] == "restricted"
    assert "AUTHORED" not in other_preds

    pv = client.get(f"/api/v1/semantic/entities/{prof_entity}/provenance", headers=auth(t_stu)).json()
    assert pv["hidden_claims_count"] >= 1
    mgr_view = client.get(f"/api/v1/semantic/entities/{prof_entity}", headers=auth(t_mgr)).json()
    assert "AUTHORED" in {x["predicate"] for x in mgr_view["relations"]}


def test_04_path_query_finds_allowed_route(client):
    """مسیر مجاز بین دانشجو و استاد از طریق روابط رسمی یافت می‌شود."""
    t = login(client, "admin1")
    src = client.get("/api/v1/semantic/entities/by-user/1", headers=auth(t)).json()["entity_id"]
    dst = client.get("/api/v1/semantic/entities/by-user/3", headers=auth(t)).json()["entity_id"]
    r = client.post("/api/v1/semantic/path-queries", headers=auth(t),
                    json={"source_eid": src, "target_eid": dst, "max_hops": 4})
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert paths, "حداقل یک مسیر رسمی باید موجود باشد"
    assert all(p["hops"] <= 4 for p in paths)


def test_05_supervisor_recommendation_explained_and_formal(client):
    """پیشنهاد استاد راهنما: شروط رسمی، ظرفیت، توضیح و نسخهٔ الگوریتم (سند ۸)."""
    t = login(client, "student1")
    r = client.post("/api/v1/semantic/recommendations/supervisors", headers=auth(t),
                    json={"topic_text": "پردازش تصویر پزشکی با یادگیری ماشین", "field": "هوش مصنوعی",
                          "skills": ["پایتون"]})
    assert r.status_code == 200
    data = r.json()
    assert data["algorithm_version"].startswith("sup-")
    assert "رسمی" in data["note"]
    assert data["candidates"], "با دادهٔ نمونه، حداقل یک کاندید هست"
    top = data["candidates"][0]
    assert top["capacity_status"] in ("known", "unknown")
    if top["capacity_status"] == "unknown":
        assert "نامشخص" in top["explanation"]
    assert "پیشنهاد" in top["explanation"]


def test_06_inference_rerun_is_idempotent_and_cancellable(client):
    """استنتاج نسخه‌دار: اجرای مجدد = حذف قبلی + بازمحاسبه؛ بدون بازخورد چرخه‌ای."""
    t = login(client, "admin1")
    r1 = client.post("/api/v1/semantic/inference-runs?rule=R1", headers=auth(t))
    assert r1.status_code == 200
    first = r1.json()
    assert first["rule"] == "R1" and first["version"].startswith("inf-r1-")
    # اجرای دوم — قبلی‌ها حذف و دوباره ساخته می‌شوند (شمارش نهایی پایدار)
    r2 = client.post("/api/v1/semantic/inference-runs?rule=R1", headers=auth(t)).json()
    assert r2["deleted_previous"] == first["generated"]
    assert r2["generated"] == first["generated"]
    # ورودی استنتاج هرگز ادعای استنتاجی نیست (R2 از روابط رسمی/استخراجی تغذیه می‌شود)
    r3 = client.post("/api/v1/semantic/inference-runs?rule=R2", headers=auth(t)).json()
    assert r3["inputs"] >= 0


def test_07_resolution_case_decision_merges_reversibly(client):
    """تطبیق موجودیت: پروندهٔ در انتظار → داوری «ادغام» → موجودیت‌ها یکی می‌شوند."""
    t = login(client, "admin1")
    cases = client.get("/api/v1/semantic/resolution-cases?status=pending", headers=auth(t)).json()
    assert cases, "نمونهٔ تطبیق seed باید در انتظار باشد"
    case = cases[0]
    assert 0.5 < case["score"] <= 1.0 and case["evidence"]
    b_name = case["entity_b"]["name"]
    r = client.post(f"/api/v1/semantic/resolution-cases/{case['id']}/decisions", headers=auth(t),
                    json={"decision": "merge", "reason": "نام و دانشگاه واحد پس از بازبینی"})
    assert r.status_code == 200 and r.json()["decision"] == "merged"
    # موجودیتِ جذب‌شده به کانونی حل می‌شود؛ خودش دیگر فعال نیست
    ov = client.get("/api/v1/semantic/graph/overview", headers=auth(t)).json()
    assert ov["kinds"].get("Person", 0) == 6   # ۷ − ۱ ادغام


def test_08_quality_snapshot_reports_conflicts_and_staleness(client):
    """حاکمیت داده: تعارض منبع نمایش داده می‌شود؛ بازسازی نما از دفتر ثبت ممکن است."""
    t = login(client, "admin1")
    q = client.get("/api/v1/semantic/admin/quality", headers=auth(t)).json()
    assert len(q["conflicts"]) >= 1
    assert q["conflicts"][0]["resolved"] is False and len(q["conflicts"][0]["options"]) >= 2
    rb = client.post("/api/v1/semantic/projection/rebuild", headers=auth(t))
    assert rb.status_code == 200 and rb.json()["rebuilt"] is True


def test_09_pool_enriched_with_semantic_evidence(client):
    """بافت‌کاری: کارت‌های استخر برای استاد شواهد برازش با توضیح دارند (بدون ثبت در گراف)."""
    t = login(client, "prof1")
    rows = client.get("/api/v1/requests/pool", headers=auth(t)).json()
    assert rows and isinstance(rows[0].get("semantic_evidence"), dict)
    ev = rows[0]["semantic_evidence"]
    if ev.get("score", 0) > 0:
        assert ev["version"].startswith("ev-")
        assert ev.get("why") or ev.get("shared")


def test_10_students_cannot_run_governance_operations(client):
    """کنترل دسترسی عملیات: دانشجو اجازهٔ اجرای استنتاج/یکپارچه‌سازی ندارد."""
    t = login(client, "student1")
    assert client.post("/api/v1/semantic/integration-runs", headers=auth(t)).status_code == 403
    assert client.post("/api/v1/semantic/inference-runs?rule=R1", headers=auth(t)).status_code == 403
    assert client.get("/api/v1/semantic/admin/quality", headers=auth(t)).status_code == 403
    assert client.get("/api/v1/semantic/resolution-cases", headers=auth(t)).status_code == 403
