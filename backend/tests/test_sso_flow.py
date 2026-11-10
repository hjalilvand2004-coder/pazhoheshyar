"""تست پایان‌به‌پایان ورود یکپارچه بر اساس سند ادغام رسمی پرتال دانشجویار۳۶۰.

یک سرور هویت کامل شبیه پرتال روی پورت واقعی (HTTP واقعی) بالا می‌آید:
Discovery + JWKS (RS256) + Authorization Code + PKCE/S256 + id_token با
nonce/iss/aud/exp + resource_access. سناریوهای پذیرش بخش ۶ سند پوشش داده می‌شوند.
"""
import base64
import hashlib
import threading
import time
import uuid
from urllib.parse import parse_qs, urlparse

import httpx
import jwt as pyjwt
import pytest
import uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient

from app.main import app

# ---------------------------------------------------------------- سرور هویت آزمایشی (شبیه پرتال دانشجویار۳۶۰)
ISSUER = None  # پس از بالا آمدن سرور روی پورت تصادفی مقدار می‌گیرد
CLIENT_ID = "pazhoheshyar360"
KID = "portal-key-1"
CODES: dict[str, dict] = {}     # code -> {sub, challenge, redirect_uri, nonce}
TOKENS: dict[str, str] = {}     # access_token -> sub

RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _int_to_b64u(x: int) -> str:
    return base64.urlsafe_b64encode(x.to_bytes((x.bit_length() + 7) // 8, "big")).decode().rstrip("=")


_pub = RSA_KEY.public_key().public_numbers()
JWKS_DOC = {"keys": [{"kty": "RSA", "use": "sig", "alg": "RS256", "kid": KID,
                      "n": _int_to_b64u(_pub.n), "e": _int_to_b64u(_pub.e)}]}

USERS_BY_SUB: dict[str, dict] = {}
CURRENT = {"sub": "kc-user-1001", "tamper": None}  # tamper: nonce|iss|aud|exp|None


def _b64u_digest(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


def _idp_app() -> FastAPI:
    idp = FastAPI(title="Mock-Portal")

    @idp.get("/.well-known/openid-configuration")
    def discovery():
        return {
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}/protocol/openid-connect/auth",
            "token_endpoint": f"{ISSUER}/protocol/openid-connect/token",
            "userinfo_endpoint": f"{ISSUER}/protocol/openid-connect/userinfo",
            "jwks_uri": f"{ISSUER}/protocol/openid-connect/certs",
            "end_session_endpoint": f"{ISSUER}/protocol/openid-connect/logout",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
        }

    @idp.get("/protocol/openid-connect/certs")
    def certs():
        return JWKS_DOC

    @idp.get("/protocol/openid-connect/auth")
    def authorize(client_id: str = "", redirect_uri: str = "", state: str = "",
                  nonce: str = "", code_challenge: str = "", code_challenge_method: str = ""):
        if client_id != CLIENT_ID:
            raise HTTPException(status_code=400, detail="کلاینت ناشناس")
        if code_challenge_method != "S256" or not code_challenge:
            raise HTTPException(status_code=400, detail="PKCE الزامی است")
        code = uuid.uuid4().hex
        CODES[code] = {"sub": CURRENT["sub"], "challenge": code_challenge,
                       "redirect_uri": redirect_uri, "nonce": nonce}
        sep = "&" if "?" in redirect_uri else "?"
        return RedirectResponse(f"{redirect_uri}{sep}code={code}&state={state}", status_code=302)

    @idp.post("/protocol/openid-connect/token")
    async def token(request: Request):
        form = await request.form()
        if form.get("client_id") != CLIENT_ID:
            raise HTTPException(status_code=401, detail="invalid_client")
        if form.get("client_secret"):  # client عمومی — secret نباید ارسال شود
            raise HTTPException(status_code=400, detail="secret_not_allowed_for_public_client")
        record = CODES.get(str(form.get("code", "")))
        if not record:
            raise HTTPException(status_code=400, detail="invalid_grant")
        verifier = str(form.get("code_verifier", ""))
        if not verifier or _b64u_digest(verifier) != record["challenge"]:
            raise HTTPException(status_code=400, detail="invalid_grant")  # PKCE mismatch
        if form.get("redirect_uri") != record["redirect_uri"]:
            raise HTTPException(status_code=400, detail="redirect_uri_mismatch")
        CODES.pop(str(form.get("code")), None)  # کد تک‌مصرف (۱۲۰ ثانیه)
        sub = record["sub"]
        profile = USERS_BY_SUB.get(sub, {})
        access = uuid.uuid4().hex
        TOKENS[access] = sub
        now = int(time.time())
        claims = {
            "iss": ISSUER, "sub": sub, "aud": CLIENT_ID, "nonce": record["nonce"],
            "iat": now, "exp": now + 300,
            "preferred_username": profile.get("preferred_username", sub),
            "name": profile.get("name", ""), "email": profile.get("email", ""),
            "resource_access": {CLIENT_ID: {"roles": profile.get("roles", [])}},
        }
        tamper = CURRENT.get("tamper")
        if tamper == "nonce":
            claims["nonce"] = "tampered-nonce"
        elif tamper == "iss":
            claims["iss"] = "http://evil:9"
        elif tamper == "aud":
            claims["aud"] = "other-system"
        elif tamper == "exp":
            claims["exp"] = now - 600
        id_token = pyjwt.encode(claims, RSA_KEY, algorithm="RS256", headers={"kid": KID})
        return {"access_token": access, "id_token": id_token, "token_type": "Bearer", "expires_in": 300}

    @idp.get("/protocol/openid-connect/userinfo")
    async def userinfo(request: Request):
        header = request.headers.get("authorization", "")
        sub = TOKENS.get(header.replace("Bearer ", "", 1).strip())
        if not sub:
            raise HTTPException(status_code=401, detail="invalid_token")
        profile = USERS_BY_SUB.get(sub, {})
        return {"sub": sub, **{k: v for k, v in profile.items() if k != "roles"}}

    return idp


@pytest.fixture(scope="module")
def idp_base_url():
    global ISSUER
    server = uvicorn.Server(uvicorn.Config(_idp_app(), host="127.0.0.1", port=0, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    ISSUER = f"http://127.0.0.1:{port}"
    USERS_BY_SUB.update({
        "kc-user-1001": {"sub": "kc-user-1001", "preferred_username": "ali.rezaei",
                         "name": "علی رضایی", "email": "ali.rezaei@univ.ac.ir", "roles": []},
        "kc-user-2002": {"sub": "kc-user-2002", "preferred_username": "sara.ahmadi",
                         "name": "سارا احمدی", "email": "sara.ahmadi@univ.ac.ir", "roles": []},
        "kc-admin-999": {"sub": "kc-admin-999", "preferred_username": "portal.admin",
                         "name": "مدیر پرتال", "email": "admin@univ.ac.ir", "roles": ["pazhoheshyar360.admin"]},
    })
    yield ISSUER
    server.should_exit = True
    thread.join(timeout=5)


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


def configure_sso(c, admin_token, enabled=True, auto_create=True,
                  redirect_uri="http://testserver/sso/callback"):
    body = {
        "enabled": enabled, "issuer": ISSUER, "client_id": CLIENT_ID,
        "client_type": "public", "client_secret": "",
        "redirect_uri": redirect_uri,
        "post_logout_redirect_uri": "http://testserver/?loggedOut=1",
        "button_label": "ورود با حساب پرتال آزمایشی",
        "scope": "openid profile email", "auto_create_users": auto_create,
        "default_roles": ["student"],
    }
    r = c.put("/api/v1/admin/sso/settings", headers=auth(admin_token), json=body)
    assert r.status_code == 200, r.text
    return r.json()


def full_sso_roundtrip(c) -> dict:
    """کل مسیر مرورگر: شروع ← پرتال (HTTP واقعی) ← بازگشت ← نشست محلی."""
    r = c.get("/api/v1/auth/sso/login", follow_redirects=False)
    assert r.status_code == 302, r.text
    authorize_url = r.headers["location"]
    assert authorize_url.startswith(f"{ISSUER}/protocol/openid-connect/auth"), authorize_url
    assert "code_challenge=" in authorize_url and "code_challenge_method=S256" in authorize_url
    assert "nonce=" in authorize_url and "state=" in authorize_url

    r2 = httpx.get(authorize_url, follow_redirects=False, timeout=10)
    assert r2.status_code == 302, r2.text
    callback_url = r2.headers["location"]
    assert callback_url.startswith("http://testserver/sso/callback"), callback_url
    qs = parse_qs(urlparse(callback_url).query)
    code, state = qs["code"][0], qs["state"][0]

    r3 = c.get(f"/api/v1/auth/sso/callback?code={code}&state={state}")
    assert r3.status_code == 200, r3.text
    return r3.json()


# ---------------------------------------------------------------- سناریوهای پذیرش

def test_01_admin_activates_sso_from_panel(client, idp_base_url):
    """سناریو ۱: فعال‌سازی از پنل + تست اتصال سبز (Discovery + JWKS)."""
    t_admin = login(client, "admin1")

    bad = client.put("/api/v1/admin/sso/settings", headers=auth(t_admin),
                     json={"enabled": True, "issuer": "", "client_id": "", "redirect_uri": ""})
    assert bad.status_code == 400

    saved = configure_sso(client, t_admin)
    assert saved["enabled"] is True and saved["client_type"] == "public"

    r = client.post("/api/v1/admin/sso/test", headers=auth(t_admin))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True, data["message"]
    assert data["jwks_keys"] >= 1
    assert data["provider"]["token_endpoint"] == f"{ISSUER}/protocol/openid-connect/token"

    pub = client.get("/api/v1/auth/sso/config").json()
    assert pub["enabled"] is True
    assert pub["button_label"] == "ورود با حساب پرتال آزمایشی"

    t_stu = login(client, "student1")
    assert client.put("/api/v1/admin/sso/settings", headers=auth(t_stu),
                      json={"enabled": False}).status_code == 403


def test_02_full_sso_login_creates_local_user(client, idp_base_url):
    """سناریوهای ۲و۳و۴: ورود کامل m.ahmadi-مانند، ساخت حساب، ورود دوم بدون حساب تکراری."""
    data = full_sso_roundtrip(client)
    user, token = data["user"], data["token"]
    assert user["username"] == "ali.rezaei"
    assert user["sso_linked"] is True
    assert "student" in user["roles"]

    me = client.get("/api/v1/auth/me", headers=auth(token))
    assert me.status_code == 200 and me.json()["id"] == user["id"]

    data2 = full_sso_roundtrip(client)
    assert data2["user"]["id"] == user["id"]  # اتصال با sub — حساب تکراری ساخته نمی‌شود


def test_03_state_tampering_rejected(client, idp_base_url):
    """سناریو ۶: دستکاری state → رد با پیام خوانا."""
    r = client.get("/api/v1/auth/sso/login", follow_redirects=False)
    authorize_url = r.headers["location"]
    r2 = httpx.get(authorize_url, follow_redirects=False, timeout=10)
    qs = parse_qs(urlparse(r2.headers["location"]).query)
    code, state = qs["code"][0], qs["state"][0]

    forged = client.get(f"/api/v1/auth/sso/callback?code={code}&state=tampered-state")
    assert forged.status_code == 400 and "state" in forged.json()["detail"]

    first = client.get(f"/api/v1/auth/sso/callback?code={code}&state={state}")
    assert first.status_code == 200

    replay = client.get(f"/api/v1/auth/sso/callback?code={code}&state={state}")
    assert replay.status_code == 400  # کد/state تک‌مصرف


def test_04_link_existing_local_account(client, idp_base_url):
    """اتصال حساب از پروفایل: کاربر محلیِ واردشده هویت SSO را به حسابش متصل می‌کند."""
    t_s2 = login(client, "student2")
    CURRENT["sub"] = "kc-user-2002"
    try:
        r = client.get(f"/api/v1/auth/sso/login?token={t_s2}", follow_redirects=False)
        assert r.status_code == 302
        authorize_url = r.headers["location"]
        r2 = httpx.get(authorize_url, follow_redirects=False, timeout=10)
        qs = parse_qs(urlparse(r2.headers["location"]).query)
        cb = client.get(f"/api/v1/auth/sso/callback?code={qs['code'][0]}&state={qs['state'][0]}")
        assert cb.status_code == 200, cb.text
        data = cb.json()
        assert data["linked"] is True and data["user"]["username"] == "student2"

        data2 = full_sso_roundtrip(client)
        assert data2["user"]["id"] == data["user"]["id"] and data2["user"]["username"] == "student2"
    finally:
        CURRENT["sub"] = "kc-user-1001"


def test_05_identity_already_bound_to_other_account(client, idp_base_url):
    """اتصال یک هویت به دو حساب رد می‌شود."""
    t_admin = login(client, "admin1")
    CURRENT["sub"] = "kc-user-2002"
    try:
        r = client.get(f"/api/v1/auth/sso/login?token={t_admin}", follow_redirects=False)
        authorize_url = r.headers["location"]
        r2 = httpx.get(authorize_url, follow_redirects=False, timeout=10)
        qs = parse_qs(urlparse(r2.headers["location"]).query)
        cb = client.get(f"/api/v1/auth/sso/callback?code={qs['code'][0]}&state={qs['state'][0]}")
        assert cb.status_code == 409 and "دیگری" in cb.json()["detail"]
    finally:
        CURRENT["sub"] = "kc-user-1001"


def test_06_wrong_pkce_verifier_rejected(client, idp_base_url):
    """سناریو ۷: PKCE نادرست / کد تک‌مصرف → خطای منقضی خوانا."""
    r = client.get("/api/v1/auth/sso/login", follow_redirects=False)
    authorize_url = r.headers["location"]
    r2 = httpx.get(authorize_url, follow_redirects=False, timeout=10)
    qs = parse_qs(urlparse(r2.headers["location"]).query)

    import app.core.oidc as oidc_mod
    pc = {"token_endpoint": f"{ISSUER}/protocol/openid-connect/token",
          "userinfo_endpoint": f"{ISSUER}/protocol/openid-connect/userinfo"}
    with pytest.raises(oidc_mod.SsoError) as ei:
        oidc_mod.exchange_code(pc, CLIENT_ID, "", qs["code"][0],
                               "http://testserver/sso/callback", code_verifier="wrong-verifier-aaaaaaaaaaaaaaa")
    assert ei.value.code in ("expired", "invalid_response")


def test_07_id_token_validation_tampering(client, idp_base_url):
    """گام ۴ سند: nonce/iss/aud/exp دستکاری‌شده → رد با پیام فارسی متناظر."""
    t_admin = login(client, "admin1")
    configure_sso(client, t_admin)
    for tamper, expected_frag in [("nonce", "nonce"), ("iss", "issuer"), ("aud", "aud"), ("exp", "منقضی")]:
        CURRENT["tamper"] = tamper
        try:
            r = client.get("/api/v1/auth/sso/login", follow_redirects=False)
            authorize_url = r.headers["location"]
            r2 = httpx.get(authorize_url, follow_redirects=False, timeout=10)
            qs = parse_qs(urlparse(r2.headers["location"]).query)
            cb = client.get(f"/api/v1/auth/sso/callback?code={qs['code'][0]}&state={qs['state'][0]}")
            assert cb.status_code == 400, f"{tamper}: {cb.status_code} {cb.text[:200]}"
            assert expected_frag in cb.json()["detail"], f"{tamper}: {cb.json()['detail']}"
        finally:
            CURRENT["tamper"] = None
    # بعد از رفع دستکاری، ورود دوباره سبز است
    data = full_sso_roundtrip(client)
    assert data["user"]["username"] in ("ali.rezaei",)


def test_08_roles_from_resource_access(client, idp_base_url):
    """گام ۵ سند: پسوند .admin → مدیر سامانه؛ بدون نقش → نقش پیش‌فرض."""
    CURRENT["sub"] = "kc-admin-999"  # نقش pazhoheshyar360.admin دارد
    try:
        data = full_sso_roundtrip(client)
        assert "system_admin" in data["user"]["roles"]
    finally:
        CURRENT["sub"] = "kc-user-1001"
    data = full_sso_roundtrip(client)  # بدون نقش → student
    assert "student" in data["user"]["roles"]


def test_09_username_based_linking(client, idp_base_url):
    """سناریو ۵ سند: حساب محلیِ هم‌نام با preferred_username وصل می‌شود (نه حساب جدید)."""
    from app.core.database import SessionLocal
    from app.models import User
    db = SessionLocal()
    local = db.query(User).filter(User.username == "m.ahmadi").one_or_none()
    if not local:
        local = User(username="m.ahmadi", display_name="م. احمدی", roles=["student"], password_hash=None)
        db.add(local)
        db.commit()
        local_id = local.id
    else:
        local_id = local.id
    db.close()

    USERS_BY_SUB["kc-new-777"] = {"sub": "kc-new-777", "preferred_username": "m.ahmadi",
                                  "name": "محمد احمدی", "email": "m.ahmadi@univ.ac.ir", "roles": []}
    CURRENT["sub"] = "kc-new-777"
    try:
        data = full_sso_roundtrip(client)
        assert data["user"]["id"] == local_id
        assert data["user"]["username"] == "m.ahmadi" and data["user"]["sso_linked"] is True
    finally:
        CURRENT["sub"] = "kc-user-1001"


def test_10_logout_returns_portal_end_session(client, idp_base_url):
    """سناریو ۹ سند: خروج → نشست محلی باطل + مسیر end_session پرتال با post_logout_redirect."""
    t = login(client, "student1")
    r = client.post("/api/v1/auth/logout", headers=auth(t))
    assert r.status_code == 200
    url = r.json().get("end_session_url", "")
    assert url.startswith(f"{ISSUER}/protocol/openid-connect/logout")
    assert "post_logout_redirect_uri=" in url


def test_11_idp_unreachable_no_crash(client, idp_base_url):
    """سناریو ۸ سند: خاموش‌بودن SSO سرور → پیام idp_unreachable بدون کرش."""
    from app.core.oidc import SsoError
    t_admin = login(client, "admin1")
    saved = configure_sso(client, t_admin)
    # موقتاً issuer را به پورت بسته تغییر می‌دهیم
    body = {"enabled": True, "issuer": "http://127.0.0.1:9", "client_id": CLIENT_ID,
            "client_type": "public", "redirect_uri": "http://testserver/sso/callback",
            "auto_create_users": True}
    r = client.put("/api/v1/admin/sso/settings", headers=auth(t_admin), json=body)
    assert r.status_code == 200
    try:
        test = client.post("/api/v1/admin/sso/test", headers=auth(t_admin))
        assert test.status_code == 200
        assert test.json()["ok"] is False
        assert "اتصال" in test.json()["message"]
        lg = client.get("/api/v1/auth/sso/login", follow_redirects=False)
        assert lg.status_code == 400
        assert "connection refused" in lg.json()["detail"] or "SSO" in lg.json()["detail"]
    finally:
        configure_sso(client, t_admin, enabled=saved["enabled"])


def test_12_disabled_blocks(client, idp_base_url):
    t_admin = login(client, "admin1")
    configure_sso(client, t_admin, enabled=False)
    try:
        assert client.get("/api/v1/auth/sso/login", follow_redirects=False).status_code == 400
        assert client.get("/api/v1/auth/sso/callback?code=x&state=y").status_code == 400
        pub = client.get("/api/v1/auth/sso/config").json()
        assert pub["enabled"] is False
    finally:
        configure_sso(client, t_admin, enabled=True)


def test_13_mirror_file_persistence(client, idp_base_url):
    """سناریو ۱۰ سند: حذف ردیف تنظیمات → بازگردانی خودکار از فایل آینه."""
    from app.core.database import SessionLocal
    from app.models import SsoSettings
    configure_sso(client, login(client, "admin1"))  # ذخیره + نوشتن فایل آینه

    db = SessionLocal()
    db.query(SsoSettings).delete()
    db.commit()
    db.close()

    r = client.get("/api/v1/admin/sso/settings", headers=auth(login(client, "admin1")))
    assert r.status_code == 200
    assert r.json()["issuer"] == ISSUER          # از فایل آینه بازگشت
    assert r.json()["client_id"] == CLIENT_ID
    assert r.json()["enabled"] is True


def test_14_initial_defaults_when_nothing_exists(client, idp_base_url):
    """در نبود جدول و فایل آینه → تنظیمات اولیهٔ پرتال (سند ادغام) ساخته می‌شود."""
    from app.core.database import SessionLocal
    from app.models import SsoSettings
    from app.core.config import SSO_PORTAL_ISSUER, SSO_PORTAL_CLIENT_ID
    from app.core.sso_store import MIRROR_FILE
    configure_sso(client, login(client, "admin1"))  # فایل آینهٔ فعلی ساخته می‌شود — بعداً حذفش می‌کنیم

    db = SessionLocal()
    db.query(SsoSettings).delete()
    db.commit()
    db.close()
    if MIRROR_FILE.exists():
        MIRROR_FILE.unlink()

    r = client.get("/api/v1/auth/sso/config")
    assert r.status_code == 200
    pub = r.json()
    assert pub["issuer"] == SSO_PORTAL_ISSUER
    assert pub["client_id"] == SSO_PORTAL_CLIENT_ID
    assert pub["client_type"] == "public"
    # بازگردانی تنظیمات ماک برای سایر تست‌ها
    configure_sso(client, login(client, "admin1"))
