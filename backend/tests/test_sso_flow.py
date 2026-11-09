"""تست پایان‌به‌پایان ورود یکپارچه (SSO/OIDC) با یک سرور هویت واقعی شبیه‌سازی‌شده Keycloak.

سناریو: فعال‌سازی SSO از پنل مدیریت ← تست اتصال ← شروع ورود ← سرور هویت (HTTP واقعی)
← بازگشت کد ← تبدیل کد به توکن ← ساخت/اتصال حساب محلی ← نشست معتبر.
"""
import threading
import time
import uuid
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient

from app.main import app

# ---------------------------------------------------------------- سرور هویت آزمایشی (شبیه Keycloak)
ISSUER = None  # پس از بالا آمدن سرور روی پورت تصادفی مقدار می‌گیرد
CLIENT_ID = "pajoohesh-yar360"
CLIENT_SECRET = "s3cr3t-keycloak-secret"
CODES: dict[str, str] = {}      # code -> sub
TOKENS: dict[str, str] = {}     # access_token -> sub
USERS_BY_SUB: dict[str, dict] = {}
CURRENT = {"sub": "kc-user-1001"}


def _idp_app() -> FastAPI:
    idp = FastAPI(title="Mock-Keycloak")

    @idp.get("/.well-known/openid-configuration")
    def discovery():
        return {
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}/authorize",
            "token_endpoint": f"{ISSUER}/token",
            "userinfo_endpoint": f"{ISSUER}/userinfo",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
        }

    @idp.get("/authorize")
    def authorize(client_id: str = "", redirect_uri: str = "", state: str = ""):
        if client_id != CLIENT_ID:
            raise HTTPException(status_code=400, detail="unknown client")
        code = uuid.uuid4().hex
        CODES[code] = {"sub": CURRENT["sub"], "redirect_uri": redirect_uri}
        sep = "&" if "?" in redirect_uri else "?"
        return RedirectResponse(f"{redirect_uri}{sep}code={code}&state={state}", status_code=302)

    @idp.post("/token")
    async def token(request: Request):
        form = await request.form()
        if form.get("client_id") != CLIENT_ID or form.get("client_secret") != CLIENT_SECRET:
            raise HTTPException(status_code=401, detail="invalid_client")
        code = str(form.get("code", ""))
        record = CODES.get(code)
        if not record:
            raise HTTPException(status_code=400, detail="invalid_or_used_code")
        if form.get("redirect_uri") != record["redirect_uri"]:
            raise HTTPException(status_code=400, detail="redirect_uri_mismatch")
        CODES.pop(code, None)  # کد یک‌بارمصرف است
        access = uuid.uuid4().hex
        TOKENS[access] = record["sub"]
        return {"access_token": access, "token_type": "Bearer", "expires_in": 300}

    @idp.get("/userinfo")
    async def userinfo(request: Request):
        header = request.headers.get("authorization", "")
        sub = TOKENS.get(header.replace("Bearer ", "", 1).strip())
        if not sub:
            raise HTTPException(status_code=401, detail="invalid_token")
        return USERS_BY_SUB.get(sub, {"sub": sub})

    return idp


@pytest.fixture(scope="module")
def idp_base_url():
    """بالا آوردن سرور هویت روی پورت تصادفی — HTTP واقعی، نه MockTransport"""
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
                         "name": "علی رضایی", "email": "ali.rezaei@univ.ac.ir"},
        "kc-user-2002": {"sub": "kc-user-2002", "preferred_username": "sara.ahmadi",
                         "name": "سارا احمدی", "email": "sara.ahmadi@univ.ac.ir"},
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


def configure_sso(c, admin_token, enabled=True, auto_create=True, redirect_uri="http://testserver/sso/callback"):
    body = {
        "enabled": enabled, "issuer": ISSUER, "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET, "redirect_uri": redirect_uri,
        "scope": "openid profile email", "auto_create_users": auto_create,
        "default_roles": ["student"],
    }
    r = c.put("/api/v1/admin/sso/settings", headers=auth(admin_token), json=body)
    assert r.status_code == 200, r.text
    return r.json()


def full_sso_roundtrip(c) -> str:
    """کل مسیر مرورگر: شروع ← سرور هویت (HTTP واقعی) ← بازگشت ← نشست محلی. توکن برمی‌گرداند."""
    r = c.get("/api/v1/auth/sso/login", follow_redirects=False)
    assert r.status_code == 302, r.text
    authorize_url = r.headers["location"]
    assert authorize_url.startswith(f"{ISSUER}/authorize"), authorize_url
    assert "state=" in authorize_url

    # مرورگر به سرور هویت می‌رود و با کد به redirect_uri بازمی‌گردد
    r2 = httpx.get(authorize_url, follow_redirects=False, timeout=10)
    assert r2.status_code == 302, r2.text
    callback_url = r2.headers["location"]
    assert callback_url.startswith("http://testserver/sso/callback"), callback_url
    qs = parse_qs(urlparse(callback_url).query)
    code, state = qs["code"][0], qs["state"][0]

    # صفحه SPA بازگشت، کد و state را به بک‌اند می‌دهد
    r3 = c.get(f"/api/v1/auth/sso/callback?code={code}&state={state}")
    assert r3.status_code == 200, r3.text
    return r3.json()


# ---------------------------------------------------------------- تست‌ها

def test_01_admin_activates_sso_from_panel(client, idp_base_url):
    """مدیر سامانه از پنل مدیریت SSO واقعی را فعال می‌کند و تست اتصال موفق است."""
    t_admin = login(client, "admin1")

    # فعال‌سازی بدون مقادیر اجباری باید رد شود
    bad = client.put("/api/v1/admin/sso/settings", headers=auth(t_admin),
                     json={"enabled": True, "issuer": "", "client_id": "", "redirect_uri": ""})
    assert bad.status_code == 400

    saved = configure_sso(client, t_admin)
    assert saved["enabled"] is True
    assert saved["client_secret_set"] is True
    assert saved["issuer"] == ISSUER

    # تست اتصال: Discovery استاندارد OIDC با HTTP واقعی خوانده می‌شود
    r = client.post("/api/v1/admin/sso/test", headers=auth(t_admin))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True, data["message"]
    assert data["provider"]["token_endpoint"] == f"{ISSUER}/token"
    assert data["provider"]["issuer_reported"] == ISSUER

    # صفحه ورود، دکمه SSO را می‌بیند
    pub = client.get("/api/v1/auth/sso/config").json()
    assert pub["enabled"] is True
    assert pub["authorization_url"] == "/api/v1/auth/sso/login"

    # غیرمدیر اجازه تغییر تنظیمات ندارد
    t_stu = login(client, "student1")
    assert client.put("/api/v1/admin/sso/settings", headers=auth(t_stu),
                      json={"enabled": False}).status_code == 403


def test_02_full_sso_login_creates_local_user(client, idp_base_url):
    """ورود کامل: کاربر جدید SSO به‌صورت خودکار ساخته می‌شود و نشست معتبر می‌گیرد."""
    data = full_sso_roundtrip(client)
    user, token = data["user"], data["token"]
    assert user["username"] == "ali.rezaei"
    assert user["sso_linked"] is True
    assert "student" in user["roles"]

    me = client.get("/api/v1/auth/me", headers=auth(token))
    assert me.status_code == 200
    assert me.json()["id"] == user["id"]

    # ورود دوم با همان هویت — همان حساب (هویت تکراری ساخته نمی‌شود)
    data2 = full_sso_roundtrip(client)
    assert data2["user"]["id"] == user["id"]


def test_03_state_is_single_use(client, idp_base_url):
    r = client.get("/api/v1/auth/sso/login", follow_redirects=False)
    authorize_url = r.headers["location"]
    r2 = httpx.get(authorize_url, follow_redirects=False, timeout=10)
    qs = parse_qs(urlparse(r2.headers["location"]).query)
    code, state = qs["code"][0], qs["state"][0]

    first = client.get(f"/api/v1/auth/sso/callback?code={code}&state={state}")
    assert first.status_code == 200

    # استفاده دوباره از همان state/کد باید رد شود
    replay = client.get(f"/api/v1/auth/sso/callback?code={code}&state={state}")
    assert replay.status_code == 400

    # state ساختگی هم رد می‌شود
    fake = client.get("/api/v1/auth/sso/callback?code=xyz&state=forged-state")
    assert fake.status_code == 400


def test_04_link_existing_local_account(client, idp_base_url):
    """اتصال حساب: کاربر محلیِ موجود (student2) هویت SSO خود را متصل می‌کند."""
    t_s2 = login(client, "student2")
    CURRENT["sub"] = "kc-user-2002"  # در سرور هویت، این بار سارا وارد می‌شود
    try:
        r = client.get(f"/api/v1/auth/sso/login?token={t_s2}", follow_redirects=False)
        assert r.status_code == 302
        authorize_url = r.headers["location"]
        r2 = httpx.get(authorize_url, follow_redirects=False, timeout=10)
        qs = parse_qs(urlparse(r2.headers["location"]).query)

        cb = client.get(f"/api/v1/auth/sso/callback?code={qs['code'][0]}&state={qs['state'][0]}")
        assert cb.status_code == 200, cb.text
        data = cb.json()
        assert data["linked"] is True
        assert data["user"]["username"] == "student2"
        assert data["user"]["sso_linked"] is True

        # ورود بعدیِ SSO با همان هویت، بدون توکن، مستقیم به حساب student2 می‌رسد
        data2 = full_sso_roundtrip(client)
        assert data2["user"]["id"] == data["user"]["id"]
        assert data2["user"]["username"] == "student2"
    finally:
        CURRENT["sub"] = "kc-user-1001"


def test_05_identity_already_bound_to_other_account(client, idp_base_url):
    """هویت SSO متصل‌شده به student2 نباید بتواند به حساب دیگری متصل شود."""
    t_admin = login(client, "admin1")
    CURRENT["sub"] = "kc-user-2002"  # همان هویتی که به student2 متصل است
    try:
        r = client.get(f"/api/v1/auth/sso/login?token={t_admin}", follow_redirects=False)
        authorize_url = r.headers["location"]
        r2 = httpx.get(authorize_url, follow_redirects=False, timeout=10)
        qs = parse_qs(urlparse(r2.headers["location"]).query)
        cb = client.get(f"/api/v1/auth/sso/callback?code={qs['code'][0]}&state={qs['state'][0]}")
        assert cb.status_code == 409
        assert "دیگری" in cb.json()["detail"]
    finally:
        CURRENT["sub"] = "kc-user-1001"


def test_06_wrong_client_secret_rejected(client, idp_base_url):
    """Secret نادرست → تبادل توکن ناموفق و خطای شفاف فارسی."""
    t_admin = login(client, "admin1")
    configure_sso(client, t_admin)  # مطمئن می‌شویم فعال است
    r = client.get("/api/v1/auth/sso/login", follow_redirects=False)
    authorize_url = r.headers["location"]
    r2 = httpx.get(authorize_url, follow_redirects=False, timeout=10)
    qs = parse_qs(urlparse(r2.headers["location"]).query)

    # دستی با secret غلط توکن بگیریم و سپس به بک‌اند ندهیم — رفتار موردانتظار: خطای تبادل
    # (شبیه‌سازی: مقدار secret را موقتاً خراب می‌کنیم)
    import app.core.oidc as oidc_mod
    pc = {"token_endpoint": f"{ISSUER}/token", "userinfo_endpoint": f"{ISSUER}/userinfo"}
    with pytest.raises(oidc_mod.SsoError):
        oidc_mod.exchange_code(pc, CLIENT_ID, "wrong-secret", qs["code"][0], "http://testserver/sso/callback")


def test_07_disabled_sso_blocks_login_and_callback(client, idp_base_url):
    t_admin = login(client, "admin1")
    configure_sso(client, t_admin, enabled=False)
    try:
        assert client.get("/api/v1/auth/sso/login", follow_redirects=False).status_code == 400
        assert client.get("/api/v1/auth/sso/callback?code=x&state=y").status_code == 400
        pub = client.get("/api/v1/auth/sso/config").json()
        assert pub["enabled"] is False
    finally:
        configure_sso(client, t_admin, enabled=True)
