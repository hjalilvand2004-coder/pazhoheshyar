"""تست‌های درس‌های مقطع‌محور — کارآموزی/درس‌پروژه/تحقیق و ارائه با چرخهٔ ارسال، بازخورد و تأیید نهایی"""
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
    return {"prof": login(client, "prof1"), "prof2": login(client, "prof2"),
            "stu_bachelor": login(client, "student2"),      # مقطع کارشناسی در seed
            "stu_master": login(client, "student1"),        # مقطع کارشناسی ارشد در seed
            "mgr": login(client, "manager1")}


def _meta(client, h):
    r = client.get("/api/v1/practicum/meta", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _create(client, h, course_type, supervisor_id, title="کارآموزی در شرکت داده‌پرداز"):
    return client.post("/api/v1/practicum/", headers=h, json={
        "course_type": course_type, "title": title, "description": "گزارش پیشرفت دوره‌ای",
        "semester": "نیم‌سال اول ۱۴۰۴-۱۴۰۵", "supervisor_id": supervisor_id})


def _submit(client, h, rec_id, note, with_file=True):
    files = []
    if with_file:
        files.append(("files", ("گزارش-نوبت.txt", f"گزارش پیشرفت نوبت: {note}".encode("utf-8"), "text/plain")))
    return client.post(f"/api/v1/practicum/{rec_id}/submissions", headers=h,
                       data={"note": note}, files=files)


def _review(client, h, sub_id, decision, feedback, score=None):
    return client.post(f"/api/v1/practicum/submissions/{sub_id}/review", headers=h,
                       json={"decision": decision, "feedback": feedback, "score": score})


def test_meta_is_degree_aware(client, tokens):
    m_b = _meta(client, auth(tokens["stu_bachelor"]))
    assert m_b["my_degree_key"] == "bachelor"
    allowed = {c["key"] for c in m_b["courses"] if c["allowed"]}
    assert allowed == {"internship", "course_project"}
    m_m = _meta(client, auth(tokens["stu_master"]))
    assert m_m["my_degree_key"] == "master"
    allowed_m = {c["key"] for c in m_m["courses"] if c["allowed"]}
    assert allowed_m == {"research_presentation"}
    m_p = _meta(client, auth(tokens["prof"]))
    assert m_p["is_student"] is False
    # کلید مقطع در /auth/me هم برای منوی مقطع‌محور برگردانده می‌شود
    me = client.get("/api/v1/auth/me", headers=auth(tokens["stu_bachelor"])).json()
    assert me["degree_key"] == "bachelor"


def test_create_record_degree_validation(client, tokens):
    h_b, h_m = auth(tokens["stu_bachelor"]), auth(tokens["stu_master"])
    prof_id = client.get("/api/v1/profiles/professors", headers=h_b).json()[0]["user_id"]
    # کارشناسی: کارآموزی مجاز، تحقیق و ارائه ممنوع
    r = _create(client, h_b, "internship", prof_id)
    assert r.status_code == 200, r.text
    assert r.json()["status_fa"] == "فعال" and r.json()["degree_fa"] == "کارشناسی"
    r = _create(client, h_b, "research_presentation", prof_id)
    assert r.status_code == 400
    # ارشد: تحقیق و ارائه مجاز، کارآموزی ممنوع
    r = _create(client, h_m, "research_presentation", prof_id, "تحقیق و ارائه — استخراج اطلاعات")
    assert r.status_code == 200
    r = _create(client, h_m, "internship", prof_id)
    assert r.status_code == 400
    # استاد نامعتبر رد می‌شود
    r = _create(client, h_b, "internship", 999999)
    assert r.status_code == 400
    # استاد حق ساختن رکورد ندارد
    r = _create(client, auth(tokens["prof"]), "internship", prof_id)
    assert r.status_code == 403


def test_full_loop_five_rounds_then_approved(client, tokens):
    h_b, h_p = auth(tokens["stu_bachelor"]), auth(tokens["prof"])
    prof_id = client.get("/api/v1/profiles/professors", headers=h_b).json()[0]["user_id"]
    rec = _create(client, h_b, "course_project", prof_id, "درس‌پروژه: داشبورد تحلیل آموزش").json()
    # پنج نوبت: چهار بار اصلاح، نوبت پنجم تأیید نهایی با نمره
    for round_no in range(1, 6):
        r = _submit(client, h_b, rec["id"], f"نسخهٔ {round_no} گزارش با اصلاحات استاد")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["submission"]["round_no"] == round_no
        assert body["record"]["status"] == "awaiting_review"
        detail = client.get(f"/api/v1/practicum/{rec['id']}", headers=h_b).json()
        sub = detail["submissions"][0]
        assert sub["status"] == "pending" and len(sub["files"]) == 1
        if round_no < 5:
            r = _review(client, h_p, sub["id"], "needs_revision",
                        f"در نوبت {round_no}: بخش تحلیل داده کامل نیست؛ اصلاح و ارسال مجدد.")
            assert r.status_code == 200, r.text
            assert r.json()["record"]["status"] == "needs_revision"
        else:
            r = _review(client, h_p, sub["id"], "approved", "کار کامل است؛ تأیید نهایی.", score=18.5)
            assert r.status_code == 200, r.text
    rec2 = client.get(f"/api/v1/practicum/{rec['id']}", headers=h_b).json()
    assert rec2["status"] == "approved" and rec2["round_count"] == 5
    assert rec2["final_score"] == 18.5 and rec2["approved_at"]
    assert rec2["submissions"][0]["status"] == "approved"
    assert rec2["submissions"][-1]["status"] == "needs_revision"
    # پس از تأیید، ارسال نوبت جدید و ارزیابی مجدد ممنوع است
    assert _submit(client, h_b, rec["id"], "ارسال بعد از تأیید").status_code == 400
    pend = next(s for s in rec2["submissions"] if s["status"] == "needs_revision")
    assert _review(client, h_p, pend["id"], "approved", "دیرهنگام").status_code == 400
    # نمرهٔ خارج از بازه رد می‌شود
    rec3 = _create(client, h_b, "internship", prof_id, "کارآموزی دوم").json()
    s = _submit(client, h_b, rec3["id"], "اولین نوبت").json()["submission"]
    assert _review(client, h_p, s["id"], "approved", "خب", score=25).status_code == 400


def test_access_control_and_file_permissions(client, tokens):
    h_b, h_m, h_p, h_p2 = (auth(tokens["stu_bachelor"]), auth(tokens["stu_master"]),
                           auth(tokens["prof"]), auth(tokens["prof2"]))
    profs = client.get("/api/v1/profiles/professors", headers=h_b).json()
    pid = {p["display_name"]: p["user_id"] for p in profs}
    sup_id = pid["دکتر سارا موسوی"]        # prof1 — استاد مربوطه
    rec = _create(client, h_b, "internship", sup_id, "کارآموزی شبکه").json()
    sub = _submit(client, h_b, rec["id"], "گزارش هفتهٔ اول").json()["submission"]
    file_id = sub["files"][0]["id"]
    # دانشجوی بیگانه و استاد غیرمربوطه حق دیدن ندارند
    assert client.get(f"/api/v1/practicum/{rec['id']}", headers=h_m).status_code == 403
    assert client.get(f"/api/v1/practicum/{rec['id']}", headers=h_p2).status_code == 403
    # استاد مربوطه می‌بیند و فایل گزارش را می‌تواند دانلود کند
    assert client.get(f"/api/v1/practicum/{rec['id']}", headers=h_p).status_code == 200
    r = client.get(f"/api/v1/files/{file_id}", headers=h_p)
    assert r.status_code == 200 and "گزارش" in r.text
    assert client.get(f"/api/v1/files/{file_id}", headers=h_m).status_code == 403
    # مدیر پژوهش دسترسی کامل مشاهده دارد
    assert client.get(f"/api/v1/practicum/{rec['id']}", headers=auth(tokens["mgr"])).status_code == 200
    # فهرست تحت ارزیابی استاد مربوطه شامل رکورد است
    sup = client.get("/api/v1/practicum/supervised", headers=h_p).json()
    assert any(x["id"] == rec["id"] for x in sup)
    # فقط استاد مربوطه ارزیابی می‌کند
    assert _review(client, h_p2, sub["id"], "approved", "نه").status_code == 403
    # دانشجو نمی‌تواند رکورد استاد دیگر را لغو کند؛ لغو رکورد خودش آزاد است
    assert client.post(f"/api/v1/practicum/{rec['id']}/cancel", headers=h_m).status_code == 403
    rec_x = _create(client, h_b, "internship", sup_id, "کارآموزی لغوشدنی").json()
    assert client.post(f"/api/v1/practicum/{rec_x['id']}/cancel", headers=h_b).json()["ok"] is True
    assert _submit(client, h_b, rec_x["id"], "بعد از لغو").status_code == 400


def test_registry_and_notifications(client, tokens):
    mods = {s["module"] for s in client.get("/api/v1/services").json()["services"]}
    assert "practicum" in mods
    # دانشجوی بدون مقطع — با خالی کردن مقطع، ساخت رکورد باید با پیام راهنما رد شود
    h_m = auth(tokens["stu_master"])
    prof_id = client.get("/api/v1/profiles/professors", headers=h_m).json()[0]["user_id"]
    saved = client.put("/api/v1/profiles/me", headers=h_m, json={"degree": ""}).json()
    assert saved["degree"] == ""
    r = _create(client, h_m, "research_presentation", prof_id)
    assert r.status_code == 400 and "پروفایل" in r.json()["detail"]
    client.put("/api/v1/profiles/me", headers=h_m, json={"degree": "کارشناسی ارشد"})
    # اعلان ارزیابی برای دانشجو ثبت شده است
    notifs = client.get("/api/v1/notifications?limit=50", headers=auth(tokens["stu_bachelor"])).json()
    assert any(n["type"] == "practicum_approved" for n in notifs)
    assert any(n["type"] == "practicum_revision" for n in notifs)
