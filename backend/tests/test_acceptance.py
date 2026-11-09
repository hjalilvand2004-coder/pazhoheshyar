"""تست‌های پذیرش اصلی — معیار: «ثبت درخواست تا تشکیل دقیقاً یک پروژه»"""
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


def test_login_ok_and_wrong_password(client):
    token = login(client, "admin1")
    assert token
    r = client.post("/api/v1/auth/login", json={"username": "admin1", "password": "bad"})
    assert r.status_code == 401


def test_role_guard_on_admin_metrics(client):
    t_stu = login(client, "student1")
    assert client.get("/api/v1/admin/metrics", headers=auth(t_stu)).status_code == 403
    t_mgr = login(client, "manager1")
    assert client.get("/api/v1/admin/metrics", headers=auth(t_mgr)).status_code == 200


def test_services_registry_public(client):
    r = client.get("/api/v1/services")
    assert r.status_code == 200
    modules = {s["module"] for s in r.json()["services"]}
    assert {"auth", "requests", "offers", "agreements", "projects", "ai", "events"} <= modules


def test_full_acceptance_flow(client):
    """دانشجو ثبت می‌کند ← استاد می‌بیند و اعلام آمادگی می‌کند ← گفت‌وگو ← انتخاب و امضای دوطرفه ← دقیقاً یک پروژه"""
    t_s2, t_p1, t_p2 = login(client, "student2"), login(client, "prof1"), login(client, "prof2")

    # ۱) ثبت و انتشار درخواست
    r = client.post("/api/v1/requests?publish_now=true", headers=auth(t_s2), json={
        "title": "مدل پیش‌بینی ترک تحصیل با داده آموزشی",
        "summary": "پیش‌بینی خطر ترک تحصیل برای پشتیبان‌یاری",
        "problem": "داده‌های آموزشی پراکنده و شناسایی دیرهنگام است.",
        "goals": "مدل قابل اتکا با گزارش دقت",
        "field": "تحلیل داده", "skills": ["آمار", "پایتون"], "scope": "all",
    })
    assert r.status_code == 200, r.text
    rid = r.json()["id"]

    # ۲) استاد در استخر می‌بیند و اعلام آمادگی می‌کند
    pool = client.get("/api/v1/requests/pool", headers=auth(t_p1)).json()
    assert any(x["id"] == rid for x in pool)
    o1 = client.post(f"/api/v1/requests/{rid}/offers", headers=auth(t_p1),
                     json={"message": "آماده همکاری هستم", "conditions": "جلسه هفتگی"}).json()
    o2 = client.post(f"/api/v1/requests/{rid}/offers", headers=auth(t_p2),
                     json={"message": "با تغییر موضوع می‌پذیرم", "conditions": ""}).json()
    req = client.get(f"/api/v1/requests/{rid}", headers=auth(t_s2)).json()
    assert req["status"] == "offers_received"

    # ۳) اعلان به دانشجو
    notes = client.get("/api/v1/notifications", headers=auth(t_s2)).json()
    assert any(n["type"] == "offer" for n in notes)

    # ۴) گفت‌وگوی مقدماتی و پذیرش استاد اول
    dlg = client.post(f"/api/v1/offers/{o1['id']}/start-dialogue", headers=auth(t_s2))
    assert dlg.status_code == 200
    conv_id = dlg.json()["conversation_id"]
    msg = client.post(f"/api/v1/conversations/{conv_id}/messages", headers=auth(t_s2),
                      json={"body": "سلام، شرایط را می‌پذیرم"}).json()
    assert msg["kind"] == "text"

    acc = client.post(f"/api/v1/offers/{o1['id']}/accept", headers=auth(t_s2))
    assert acc.status_code == 200, acc.text
    assert acc.json()["request"]["status"] == "initial_agreement"

    # ۵) پذیرش پیشنهاد دیگر باید مسدود شود (اتصال متعارض)
    assert client.post(f"/api/v1/offers/{o2['id']}/accept", headers=auth(t_s2)).status_code == 409

    # ۶) امضای دوطرفه توافق‌نامه
    agr = client.get(f"/api/v1/agreements/by-request/{rid}", headers=auth(t_s2)).json()
    aid = agr["id"]
    assert client.post(f"/api/v1/agreements/{aid}/sign", headers=auth(t_s2)).json()["next"] == "waiting_other_party"
    signed = client.post(f"/api/v1/agreements/{aid}/sign", headers=auth(t_p1)).json()
    assert signed["next"] == "project_formed", signed
    project_id = signed["project_id"]

    # ۷) دقیقاً یک پروژه معتبر
    mine = client.get("/api/v1/projects/mine", headers=auth(t_s2)).json()
    assert len(mine) == 1 and mine[0]["id"] == project_id
    req = client.get(f"/api/v1/requests/{rid}", headers=auth(t_s2)).json()
    assert req["status"] == "connected_to_project"

    # ۸) دسترسی پروژه فقط برای اعضای مجاز
    t_s1 = login(client, "student1")
    assert client.get(f"/api/v1/projects/{project_id}", headers=auth(t_s1)).status_code == 403
    assert client.get(f"/api/v1/projects/{project_id}", headers=auth(t_p1)).status_code == 200

    # ۹) فضای پروژه: وظیفه، جلسه، پیشرفت
    task = client.post(f"/api/v1/projects/{project_id}/tasks", headers=auth(t_p1),
                       json={"title": "مرور ادبیات", "assignee_id": None}).json()
    assert client.patch(f"/api/v1/projects/{project_id}/tasks/{task['id']}", headers=auth(t_p1),
                        json={"status": "done"}).status_code == 200
    rep = client.post(f"/api/v1/projects/{project_id}/progress", headers=auth(t_s2),
                      json={"percent": 25, "note": "شروع شد"}).json()
    assert rep["percent"] == 25


def test_university_approval_path(client):
    """مسیر تأیید دانشگاه: امضای دوطرفه ← در انتظار تأیید ← مدیر تأیید می‌کند ← پروژه"""
    t_s1, t_p1, t_mgr = login(client, "student1"), login(client, "prof1"), login(client, "manager1")

    reqs = client.get("/api/v1/requests/mine", headers=auth(t_s1)).json()
    rid = next(r["id"] for r in reqs if r["university_approval_required"])
    offers = client.get(f"/api/v1/requests/{rid}/offers", headers=auth(t_s1)).json()
    oid = offers[0]["id"]

    assert client.post(f"/api/v1/offers/{oid}/accept", headers=auth(t_s1)).status_code == 200
    aid = client.get(f"/api/v1/agreements/by-request/{rid}", headers=auth(t_s1)).json()["id"]
    client.post(f"/api/v1/agreements/{aid}/sign", headers=auth(t_s1))
    r = client.post(f"/api/v1/agreements/{aid}/sign", headers=auth(t_p1)).json()
    assert r["next"] == "pending_university_approval"
    assert client.get(f"/api/v1/projects/mine", headers=auth(t_s1)).json() == []

    approved = client.post(f"/api/v1/requests/{rid}/approve", headers=auth(t_mgr))
    assert approved.status_code == 200
    mine = client.get("/api/v1/projects/mine", headers=auth(t_s1)).json()
    assert len(mine) == 1

    # تأیید تکراری باید رد شود
    assert client.post(f"/api/v1/requests/{rid}/approve", headers=auth(t_mgr)).status_code == 400


def test_secret_details_access_control(client):
    """استاد بدون پیشنهاد و بدون اجازه، نه جزئیات می‌بیند و نه محرمانه"""
    t_s1, t_p2 = login(client, "student1"), login(client, "prof2")
    reqs = client.get("/api/v1/requests/mine", headers=auth(t_s1)).json()
    rid = next(r["id"] for r in reqs if r.get("secret_details"))
    d = client.get(f"/api/v1/requests/{rid}", headers=auth(t_p2)).json()
    assert "secret_details" not in d  # بدون اجازه صاحب درخواست


def test_secret_share_works(client):
    t_s1, t_p1 = login(client, "student1"), login(client, "prof1")
    reqs = client.get("/api/v1/requests/mine", headers=auth(t_s1)).json()
    rid = next(r["id"] for r in reqs if r.get("secret_details"))
    me = client.get("/api/v1/auth/me", headers=auth(t_p1)).json()
    assert client.post(f"/api/v1/requests/{rid}/share-secret", headers=auth(t_s1),
                       json={"professor_id": me["id"]}).status_code == 200
    d = client.get(f"/api/v1/requests/{rid}", headers=auth(t_p1)).json()
    assert "secret_details" in d


def test_ai_match_returns_reasons_and_demo_label(client):
    t_s2, t_p1 = login(client, "student2"), login(client, "prof1")
    reqs = client.get("/api/v1/requests/mine", headers=auth(t_s2)).json()
    rid = reqs[0]["id"]  # درخواست student2 در seed فعال نیست؛ از student1 استفاده می‌کنیم
    t_s1 = login(client, "student1")
    reqs = client.get("/api/v1/requests/mine", headers=auth(t_s1)).json()
    rid = next(r["id"] for r in reqs if r["status"] == "connected_to_project")
    out = client.get(f"/api/v1/ai/match-professors/{rid}", headers=auth(t_s1)).json()
    assert out["demo"] is True
    for s in out["suggestions"]:
        assert s["reasons"]


def test_events_feed_requires_manager(client):
    t_stu, t_mgr = login(client, "student1"), login(client, "manager1")
    assert client.get("/api/v1/events", headers=auth(t_stu)).status_code == 403
    r = client.get("/api/v1/events", headers=auth(t_mgr))
    assert r.status_code == 200
    types = {e["type"] for e in r.json()}
    assert "project_formed" in types
