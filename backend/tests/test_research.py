"""تست‌های فضای پژوهش تیمی — نگارش مشترک، قالب‌های استاندارد، دستیار نگارش و انتشار در شبکهٔ دانش"""
import io
import zipfile

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
            "stu": login(client, "student1"), "stu2": login(client, "student2"),
            "mgr": login(client, "manager1"), "adm": login(client, "admin1")}


def _new_doc(client, h, **kw):
    body = {"title": "پیش‌بینی ترک تحصیل با یادگیری ماشین — مقاله کنفرانسی",
            "template": "ieee-conference", "venue_note": "IEEE کنفرانس داده آموزشی"}
    body.update(kw)
    r = client.post("/api/v1/research/docs", headers=h, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_templates_list_and_skeleton(client, tokens):
    r = client.get("/api/v1/research/templates", headers=auth(tokens["stu"]))
    assert r.status_code == 200
    keys = {t["key"] for t in r.json()}
    assert {"ieee-conference", "ieee-journal", "springer-lncs", "springer-article", "apa-article", "fa-thesis"} <= keys
    d = _new_doc(client, auth(tokens["prof"]))
    assert d["status_fa"] == "پیش‌نویس"
    detail = client.get(f"/api/v1/research/docs/{d['id']}", headers=auth(tokens["prof"])).json()
    assert len(detail["sections"]) == 6  # اسکلت IEEE کنفرانس
    assert detail["members"][0]["role"] == "lead"
    assert detail["my_role"] == "lead"


def test_team_roles_and_access_control(client, tokens):
    h_p, h_s, h_s2 = auth(tokens["prof"]), auth(tokens["stu"]), auth(tokens["stu2"])
    d = _new_doc(client, h_p)
    # دانشجوی بیگانه حق دیدن ندارد
    assert client.get(f"/api/v1/research/docs/{d['id']}", headers=h_s2).status_code == 403
    # دعوت دانشجو به‌عنوان نویسنده
    r = client.post(f"/api/v1/research/docs/{d['id']}/members", headers=h_p,
                    json={"username": "student1", "role": "writer"})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/v1/research/docs/{d['id']}", headers=h_s).status_code == 200
    # دانشجو نمی‌تواند عضو اضافه کند یا وضعیت را تأیید کند
    r = client.post(f"/api/v1/research/docs/{d['id']}/members", headers=h_s,
                    json={"username": "student2", "role": "observer"})
    assert r.status_code == 403
    r = client.patch(f"/api/v1/research/docs/{d['id']}", headers=h_s, json={"action": "approve"})
    assert r.status_code in (400, 403)
    # نقش ناظر: می‌بیند و دیدگاه می‌دهد اما نمی‌تواند بنویسد
    client.post(f"/api/v1/research/docs/{d['id']}/members", headers=h_p,
                json={"username": "student2", "role": "observer"})
    r = client.post(f"/api/v1/research/docs/{d['id']}/comments", headers=h_s2,
                    json={"body": "پیشنهاد می‌کنم بخش مقایسه اضافه شود"})
    assert r.status_code == 200
    sid = client.get(f"/api/v1/research/docs/{d['id']}", headers=h_s).json()["sections"][0]
    r = client.patch(f"/api/v1/research/docs/{d['id']}/sections/{sid['id']}", headers=h_s2,
                     json={"body": "متن ناظر"})
    assert r.status_code == 403


def test_section_edit_optimistic_lock(client, tokens):
    h_p, h_s = auth(tokens["prof"]), auth(tokens["stu"])
    d = _new_doc(client, h_p)
    client.post(f"/api/v1/research/docs/{d['id']}/members", headers=h_p,
                json={"username": "student1", "role": "writer"})
    detail = client.get(f"/api/v1/research/docs/{d['id']}", headers=h_s).json()
    s = detail["sections"][1]
    r = client.patch(f"/api/v1/research/docs/{d['id']}/sections/{s['id']}", headers=h_s,
                     json={"body": "نسخهٔ دانشجو", "base_version_no": s["version_no"]})
    assert r.status_code == 200, r.text
    new_v = r.json()["version_no"]
    # استاد با نسخهٔ قدیمی می‌زند → تعارض
    r = client.patch(f"/api/v1/research/docs/{d['id']}/sections/{s['id']}", headers=h_p,
                     json={"body": "نسخهٔ قدیمی استاد", "base_version_no": s["version_no"]})
    assert r.status_code == 409
    assert r.json()["detail"]["current_version_no"] == new_v
    # با نسخهٔ تازه درست می‌شود
    r = client.patch(f"/api/v1/research/docs/{d['id']}/sections/{s['id']}", headers=h_p,
                     json={"body": "مکمل استاد", "base_version_no": new_v})
    assert r.status_code == 200


def test_versions_snapshot_and_restore(client, tokens):
    h_p, h_s = auth(tokens["prof"]), auth(tokens["stu"])
    d = _new_doc(client, h_p)
    client.post(f"/api/v1/research/docs/{d['id']}/members", headers=h_p,
                json={"username": "student1", "role": "writer"})
    detail = client.get(f"/api/v1/research/docs/{d['id']}", headers=h_s).json()
    s = detail["sections"][0]
    client.patch(f"/api/v1/research/docs/{d['id']}/sections/{s['id']}", headers=h_s,
                 json={"body": "متن نسخهٔ اول", "base_version_no": s["version_no"]})
    r = client.post(f"/api/v1/research/docs/{d['id']}/versions", headers=h_s, json={"label": "قبل از داوری"})
    assert r.status_code == 200, r.text
    vid = r.json()["id"]
    s2 = client.get(f"/api/v1/research/docs/{d['id']}", headers=h_s).json()["sections"][0]
    client.patch(f"/api/v1/research/docs/{d['id']}/sections/{s2['id']}", headers=h_s,
                 json={"body": "متن ویرایش دوم", "base_version_no": s2["version_no"]})
    r = client.post(f"/api/v1/research/docs/{d['id']}/versions/{vid}/restore", headers=h_p)
    assert r.status_code == 200, r.text
    body = client.get(f"/api/v1/research/docs/{d['id']}", headers=h_p).json()["sections"][0]["body"]
    assert body == "متن نسخهٔ اول"


def test_references_and_citation_styles(client, tokens):
    h_p = auth(tokens["prof"])
    d = _new_doc(client, h_p, template="springer-lncs", language="en")
    for ref in [{"authors": "Vahdat, A.; Becker, D.", "title": "Epidemic routing for partially connected ad hoc networks",
                 "venue": "Duke Univ. Tech. Rep.", "year": "2000"},
                {"authors": "Zhang, J.; Wang, Y.", "title": "Dropout prediction in MOOCs", "venue": "Comput. Educ.",
                 "year": "2022", "doi": "10.1016/j.compedu.2022.104583"}]:
        r = client.post(f"/api/v1/research/docs/{d['id']}/references", headers=h_p, json=ref)
        assert r.status_code == 200, r.text
    # DOI نامعتبر رد می‌شود
    r = client.post(f"/api/v1/research/docs/{d['id']}/references", headers=h_p,
                    json={"title": "بدون doi درست", "doi": "not-a-doi"})
    assert r.status_code == 400
    r = client.get(f"/api/v1/research/docs/{d['id']}/references/formatted?style=ieee", headers=h_p)
    assert r.status_code == 200
    items = r.json()["items"]
    assert items[0]["formatted"].startswith("[1] ") and "Epidemic routing" in items[0]["formatted"]
    assert "https://doi.org/10.1016" in items[1]["formatted"]
    r = client.get(f"/api/v1/research/docs/{d['id']}/references/formatted?style=apa", headers=h_p)
    assert "(2022)." in r.json()["items"][1]["formatted"]
    r = client.get(f"/api/v1/research/docs/{d['id']}/references/formatted?style=mla", headers=h_p)
    assert r.status_code == 400


def test_export_formats(client, tokens):
    h_p = auth(tokens["prof"])
    d = _new_doc(client, h_p)
    did = d["id"]
    detail = client.get(f"/api/v1/research/docs/{did}", headers=h_p).json()
    s = detail["sections"][0]
    client.patch(f"/api/v1/research/docs/{did}/sections/{s['id']}", headers=h_p,
                 json={"body": "First paragraph of the abstract about dropout prediction.",
                       "base_version_no": s["version_no"]})
    client.post(f"/api/v1/research/docs/{did}/references", headers=h_p,
                json={"authors": "Zhang, J.; Wang, Y.", "title": "Dropout prediction in MOOCs",
                      "venue": "Comput. Educ.", "year": "2022"})
    r = client.get(f"/api/v1/research/docs/{did}/export?format=tex", headers=h_p)
    assert r.status_code == 200 and "\\documentclass[conference]{IEEEtran}" in r.text
    assert "thebibliography" in r.text and "IEEEtran" in r.text
    r = client.get(f"/api/v1/research/docs/{did}/export?format=html", headers=h_p)
    assert r.status_code == 200 and "column-count:2" in r.text and "dropout prediction" in r.text
    r = client.get(f"/api/v1/research/docs/{did}/export?format=docx", headers=h_p)
    assert r.status_code == 200 and r.content[:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert "dropout prediction" in xml
    # قالب فارسی — RTL و XePersian
    df = _new_doc(client, h_p, template="fa-thesis", language="fa")
    r = client.get(f"/api/v1/research/docs/{df['id']}/export?format=html", headers=h_p)
    assert 'dir="rtl"' in r.text and "xepersian" in client.get(
        f"/api/v1/research/docs/{df['id']}/export?format=tex", headers=h_p).text
    r = client.get(f"/api/v1/research/docs/{did}/export?format=pdf", headers=h_p)
    assert r.status_code == 400


def test_doc_status_workflow_requires_lead(client, tokens):
    h_p, h_s = auth(tokens["prof"]), auth(tokens["stu"])
    d = _new_doc(client, h_p)
    client.post(f"/api/v1/research/docs/{d['id']}/members", headers=h_p,
                json={"username": "student1", "role": "writer"})
    # گذار نامعتبر
    r = client.patch(f"/api/v1/research/docs/{d['id']}", headers=h_p, json={"action": "approve"})
    assert r.status_code == 400
    assert client.patch(f"/api/v1/research/docs/{d['id']}", headers=h_p,
                        json={"action": "submit_review"}).status_code == 200
    assert client.patch(f"/api/v1/research/docs/{d['id']}", headers=h_p,
                        json={"action": "mark_revised"}).status_code == 200
    # دانشجو نمی‌تواند تأیید کند
    r = client.patch(f"/api/v1/research/docs/{d['id']}", headers=h_s, json={"action": "approve"})
    assert r.status_code in (400, 403)
    assert client.patch(f"/api/v1/research/docs/{d['id']}", headers=h_p,
                        json={"action": "approve"}).status_code == 200
    # انتشار پیش از تأیید ممنوع است؛ بعد از تأیید ممکن
    d2 = _new_doc(client, h_p)
    r = client.post(f"/api/v1/research/docs/{d2['id']}/publish", headers=h_p)
    assert r.status_code == 400


def test_publish_creates_semantic_publication(client, tokens):
    """با prof2/student2 اجرا می‌شود تا رابطهٔ asserted نویسندگی، تست‌های حساسیت پروفایل
    prof1 در test_semantic را آلوده نکند (تست ۰۳ اولین AUTHORED را بررسی می‌کند)."""
    h_p = auth(tokens["prof2"])
    d = _new_doc(client, h_p, template="springer-lncs", language="en")
    did = d["id"]
    client.post(f"/api/v1/research/docs/{did}/references", headers=h_p,
                json={"title": "Dropout prediction with neural networks", "authors": "Zhang, J.",
                      "venue": "Comput. Educ.", "year": "2022"})
    client.post(f"/api/v1/research/docs/{did}/members", headers=h_p,
                json={"username": "student2", "role": "writer"})
    for a in ["submit_review", "mark_revised", "approve"]:
        assert client.patch(f"/api/v1/research/docs/{did}", headers=h_p, json={"action": a}).status_code == 200
    r = client.post(f"/api/v1/research/docs/{did}/publish", headers=h_p)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["authors"] == 2 and body["semantic_entity_id"]
    # در جست‌وجوی معنایی پیدا می‌شود
    r = client.get("/api/v1/semantic/search", headers=h_p,
                   params={"q": "پیش‌بینی ترک تحصیل با یادگیری ماشین"})
    assert r.status_code == 200
    flat = str(r.json())
    assert body["semantic_entity_id"] in flat or "Publication" in flat
    # رخداد semantic_outbox ثبت شده است
    r = client.get("/api/v1/events", headers=auth(tokens["mgr"]))
    assert r.status_code == 200
    assert any(e.get("type") == "semantic_outbox" for e in r.json())


def test_writing_ai_endpoints(client, tokens):
    h_p = auth(tokens["prof"])
    d = _new_doc(client, h_p, template="fa-thesis", language="fa")
    did = d["id"]
    detail = client.get(f"/api/v1/research/docs/{did}", headers=h_p).json()
    s = detail["sections"][1]  # مقدمه
    client.patch(f"/api/v1/research/docs/{did}/sections/{s['id']}", headers=h_p,
                 json={"body": "ترک تحصیل مسئله‌ای مهم در دانشگاه است. پژوهش‌های پیشین بر مدل‌های آماری تکیه داشته‌اند."
                              " در این پژوهش مدل یادگیری ماشین پیشنهاد می‌شود که با داده آموزشی آموزش می‌بیند.",
                       "base_version_no": s["version_no"]})
    r = client.post("/api/v1/ai/doc-outline", headers=h_p, json={"doc_id": did})
    assert r.status_code == 200 and r.json()["engine"] == "doc-ai-1.0.0"
    assert r.json()["progress"]["filled_sections"] == 1
    r = client.post("/api/v1/ai/doc-feedback", headers=h_p, json={"doc_id": did})
    assert r.status_code == 200 and any("هنوز نوشته نشده" in i for i in r.json()["issues"])
    r = client.post("/api/v1/ai/doc-abstract", headers=h_p, json={"doc_id": did})
    assert r.status_code == 200 and len(r.json()["abstract_scaffold"]) >= 1
    r = client.post("/api/v1/ai/doc-keywords", headers=h_p, json={"doc_id": did})
    assert r.status_code == 200 and len(r.json()["suggestions"]) >= 1
    r = client.post("/api/v1/ai/doc-related-work", headers=h_p, json={"doc_id": did})
    assert r.status_code == 200 and "مرجعی ثبت نشده" in r.json()["scaffold"][0]
    # دسترسی: دانشجوی بیگانه ممنوع
    r = client.post("/api/v1/ai/doc-outline", headers=auth(tokens["stu2"]), json={"doc_id": did})
    assert r.status_code == 403


def test_research_module_in_services_registry(client):
    r = client.get("/api/v1/services")
    assert r.status_code == 200
    mods = {s["module"]: s for s in r.json()["services"]}
    assert "research" in mods
    assert any("export" in e for e in mods["research"]["endpoints"])
    assert any("doc-outline" in e for e in mods["ai"]["endpoints"])
