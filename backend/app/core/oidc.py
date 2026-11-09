"""اتصال ورود یکپارچه (SSO) با Keycloak / OIDC — تنظیم‌شونده از پنل مدیریت"""
import time

import httpx

_wellknown_cache: dict[str, tuple[float, dict]] = {}


class SsoError(Exception):
    pass


def get_provider_config(issuer: str) -> dict:
    """خواندن discovery استاندارد OIDC با کش کوتاه‌مدت"""
    if not issuer:
        raise SsoError("آدرس Issuer تنظیم نشده است")
    now = time.time()
    cached = _wellknown_cache.get(issuer)
    if cached and now - cached[0] < 600:
        return cached[1]
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    try:
        resp = httpx.get(url, timeout=8)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # شبکه، آدرس نادرست و …
        raise SsoError(f"دریافت تنظیمات SSO ناموفق بود: {exc}") from exc
    _wellknown_cache[issuer] = (now, data)
    return data


def build_auth_url(pc: dict, client_id: str, redirect_uri: str, scope: str, state: str) -> str:
    from urllib.parse import quote
    ep = pc.get("authorization_endpoint")
    if not ep:
        raise SsoError("authorization_endpoint در تنظیمات سرور SSO یافت نشد")
    return (
        f"{ep}?response_type=code&client_id={quote(client_id)}"
        f"&redirect_uri={quote(redirect_uri)}&scope={quote(scope or 'openid profile')}&state={quote(state)}"
    )


def exchange_code(pc: dict, client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    ep = pc.get("token_endpoint")
    if not ep:
        raise SsoError("token_endpoint یافت نشد")
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    try:
        resp = httpx.post(ep, data=data, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        raise SsoError(f"تبدیل کد به توکن ناموفق بود: {exc}") from exc


def fetch_userinfo(pc: dict, access_token: str) -> dict:
    ep = pc.get("userinfo_endpoint")
    if not ep:
        raise SsoError("userinfo_endpoint یافت نشد")
    try:
        resp = httpx.get(ep, headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        raise SsoError(f"دریافت هویت کاربر ناموفق بود: {exc}") from exc
