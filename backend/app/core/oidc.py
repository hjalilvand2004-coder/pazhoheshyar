"""اتصال ورود یکپارچه (SSO) با پرتال دانشجویار۳۶۰ / هر سرور OIDC استاندارد.

طبق سند ادغام رسمی: Authorization Code Flow + PKCE (S256)، Discovery با
مقایسهٔ سخت‌گیرانهٔ issuer، اعتبارسنجی کامل id_token (RS256 از jwks_uri
با کش ≤۱ ساعت، iss/aud/nonce/exp/iat/sub) و نگاشت خطاها به پیام فارسی.
"""
import base64
import hashlib
import json
import secrets
import time

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

from .config import SSO_JWKS_CACHE_SECONDS

_wellknown_cache: dict[str, tuple[float, dict]] = {}
_jwks_cache: dict[str, tuple[float, dict]] = {}


class SsoError(Exception):
    """خطای SSO با کد قابل‌نگاشت به پیام فارسی خوانا (کاربر هرگز خطای خام نمی‌بیند)."""

    def __init__(self, code: str, detail: str = ""):
        self.code = code  # disabled|state|expired|rate|idp_unreachable|iss|aud|nonce|invalid_response|config
        self.detail = detail
        super().__init__(detail or code)


ERROR_MESSAGES_FA = {
    "disabled": "ورود یکپارچه غیرفعال است؛ مدیر سامانه باید از پنل مدیریت آن را فعال کند.",
    "config": "تنظیمات ورود یکپارچه کامل نیست؛ از مدیر سامانه پیگیری کنید.",
    "state": "نشست ورود نامعتبر است (state)؛ دوباره روی دکمهٔ ورود یکپارچه بزنید.",
    "nonce": "اعتبارسنجی نشست ورود ناموفق بود (nonce)؛ دوباره تلاش کنید.",
    "expired": "نشست ورود منقضی شده است — دوباره تلاش کنید. (کد مجوز فقط ۱۲۰ ثانیه و یک‌بارمصرف است)",
    "rate": "تلاش‌های ورود زیاد بوده است؛ کمی بعد دوباره تلاش کنید.",
    "idp_unreachable": "اتصال به سرور SSO برقرار نشد (connection refused)؛ مطمئن شوید سرویس پرتال (RUN-PORTAL.bat) روی سرور اجرا است و پورت 8086 باز است.",
    "iss": "هویت سرور SSO با پیکربندی مطابقت ندارد (issuer)؛ مقدار Issuer را در پنل مدیریت بازبینی کنید.",
    "aud": "توکن صادرشده برای این سامانه نیست (aud)؛ Client ID را بازبینی کنید.",
    "invalid_response": "پاسخ سرور SSO معتبر نیست؛ ورود ناموفق بود. دوباره تلاش کنید.",
    "access_denied": "ورود لغو شد (شما اجازه ندادید یا سرور هویت خطا برگرداند).",
}


def error_message(code: str) -> str:
    return ERROR_MESSAGES_FA.get(code, "ورود یکپارچه ناموفق بود؛ دوباره تلاش کنید.")


# ---------------------------------------------------------------- PKCE (S256)
def generate_pkce() -> tuple[str, str]:
    """(code_verifier, code_challenge) — verifier با طول ۶۴ از الفبای مجاز RFC 7636."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    verifier = "".join(secrets.choice(alphabet) for _ in range(64))
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


# ---------------------------------------------------------------- Discovery
def get_provider_config(issuer: str) -> dict:
    """Discovery استاندارد OIDC با کش کوتاه‌مدت + مقایسهٔ سخت‌گیرانهٔ issuer."""
    if not issuer:
        raise SsoError("config", "issuer خالی است")
    now = time.time()
    cached = _wellknown_cache.get(issuer)
    if cached and now - cached[0] < 600:
        return cached[1]
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    try:
        resp = httpx.get(url, timeout=8)
        resp.raise_for_status()
        data = resp.json()
    except httpx.ConnectError as exc:
        raise SsoError("idp_unreachable", str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        code = "rate" if exc.response.status_code == 429 else "idp_unreachable"
        raise SsoError(code, str(exc)) from exc
    except Exception as exc:  # آدرس نادرست، JSON خراب و …
        raise SsoError("idp_unreachable", str(exc)) from exc
    # مقایسهٔ رشته‌ایِ دقیق؛ فقط تفاوت یک اسلش انتهایی بخشیده می‌شود
    if str(data.get("issuer", "")).rstrip("/") != issuer.rstrip("/"):
        raise SsoError("iss", f"discovery issuer={data.get('issuer')} ≠ config={issuer}")
    _wellknown_cache[issuer] = (now, data)
    return data


# ---------------------------------------------------------------- JWKS با کش ≤۱ ساعت
def get_jwks(jwks_uri: str, force: bool = False) -> dict:
    if not jwks_uri:
        raise SsoError("config", "jwks_uri یافت نشد")
    now = time.time()
    cached = _jwks_cache.get(jwks_uri)
    if cached and not force and now - cached[0] < SSO_JWKS_CACHE_SECONDS:
        return cached[1]
    try:
        resp = httpx.get(jwks_uri, timeout=8)
        resp.raise_for_status()
        data = resp.json()
    except httpx.ConnectError as exc:
        raise SsoError("idp_unreachable", str(exc)) from exc
    except Exception as exc:
        raise SsoError("idp_unreachable", str(exc)) from exc
    _jwks_cache[jwks_uri] = (now, data)
    return data


# ---------------------------------------------------------------- ساخت URL ورود
def build_auth_url(pc: dict, client_id: str, redirect_uri: str, scope: str, state: str,
                   nonce: str = "", code_challenge: str = "") -> str:
    from urllib.parse import quote
    ep = pc.get("authorization_endpoint")
    if not ep:
        raise SsoError("invalid_response", "authorization_endpoint یافت نشد")
    url = (
        f"{ep}?response_type=code&client_id={quote(client_id)}"
        f"&redirect_uri={quote(redirect_uri)}&scope={quote(scope or 'openid profile email')}&state={quote(state)}"
    )
    if nonce:
        url += f"&nonce={quote(nonce)}"
    if code_challenge:
        url += f"&code_challenge={quote(code_challenge)}&code_challenge_method=S256"
    return url


# ---------------------------------------------------------------- تبادل کد (سمت سرور سامانه)
def exchange_code(pc: dict, client_id: str, client_secret: str, code: str, redirect_uri: str,
                  code_verifier: str = "") -> dict:
    ep = pc.get("token_endpoint")
    if not ep:
        raise SsoError("invalid_response", "token_endpoint یافت نشد")
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,   # دقیقاً همان رشتهٔ ثبت‌شده — کوچک‌ترین تفاوت خطا می‌دهد
        "client_id": client_id,
    }
    if client_secret:                    # client عمومی: secret ارسال نمی‌شود
        data["client_secret"] = client_secret
    if code_verifier:                    # PKCE — الزامی برای client عمومی
        data["code_verifier"] = code_verifier
    try:
        resp = httpx.post(ep, data=data, timeout=10)
        if resp.status_code == 429:
            raise SsoError("rate")
        if resp.status_code >= 400:
            body = ""
            try:
                body = str(resp.json().get("error", ""))
            except Exception:
                body = resp.text[:120]
            code_err = "expired" if body in ("invalid_grant", "invalid_code") else "invalid_response"
            raise SsoError(code_err, f"token {resp.status_code}: {body}")
        return resp.json()
    except httpx.ConnectError as exc:
        raise SsoError("idp_unreachable", str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise SsoError("idp_unreachable", str(exc)) from exc


# ---------------------------------------------------------------- اعتبارسنجی id_token (گام ۴ سند — هیچ‌یک حذف نمی‌شود)
def validate_id_token(id_token: str, *, issuer: str, client_id: str,
                      expected_nonce: str, jwks_uri: str) -> dict:
    try:
        header = jwt.get_unverified_header(id_token)
    except Exception as exc:
        raise SsoError("invalid_response", f"header: {exc}") from exc
    if header.get("alg") != "RS256":
        raise SsoError("invalid_response", f"alg={header.get('alg')} ≠ RS256")
    kid = header.get("kid")

    keys = get_jwks(jwks_uri).get("keys", [])
    jwk = next((k for k in keys if k.get("kid") == kid), None)
    if jwk is None and kid:
        # نبود kid → یک‌بار تازه‌گیری اجباری JWKS (چرخش کلید بی‌دردسر)
        keys = get_jwks(jwks_uri, force=True).get("keys", [])
        jwk = next((k for k in keys if k.get("kid") == kid), None)
    if not jwk:
        raise SsoError("invalid_response", f"کلید امضا با kid={kid} در JWKS یافت نشد")

    try:
        key = RSAAlgorithm.from_jwk(json.dumps(jwk))
        claims = jwt.decode(id_token, key, algorithms=["RS256"],
                            options={"verify_aud": False, "verify_iss": False})
    except jwt.ExpiredSignatureError as exc:
        raise SsoError("expired", "id_token منقضی است") from exc
    except jwt.InvalidTokenError as exc:
        raise SsoError("invalid_response", f"امضا/ساختار: {exc}") from exc

    now = time.time()
    if float(claims.get("exp") or 0) < now - 30:
        raise SsoError("expired", "id_token منقضی است")
    if float(claims.get("iat") or 0) > now + 900:  # تحمل اختلاف ساعت سرورها تا ~۱۵ دقیقه
        raise SsoError("invalid_response", "iat در آینده است")
    if str(claims.get("iss", "")).rstrip("/") != issuer.rstrip("/"):
        raise SsoError("iss", f"token iss={claims.get('iss')} ≠ config={issuer}")
    aud = claims.get("aud")
    aud_list = aud if isinstance(aud, list) else [aud]
    if client_id not in aud_list:
        raise SsoError("aud", f"aud={aud} ≠ client_id={client_id}")
    if expected_nonce and claims.get("nonce") != expected_nonce:
        raise SsoError("nonce", "عدم تطابق nonce")
    if not claims.get("sub"):
        raise SsoError("invalid_response", "sub خالی است")
    return claims


def fetch_userinfo(pc: dict, access_token: str) -> dict:
    ep = pc.get("userinfo_endpoint")
    if not ep:
        raise SsoError("invalid_response", "userinfo_endpoint یافت نشد")
    try:
        resp = httpx.get(ep, headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
        if resp.status_code == 429:
            raise SsoError("rate")
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError as exc:
        raise SsoError("idp_unreachable", str(exc)) from exc
    except SsoError:
        raise
    except Exception as exc:
        # userinfo اختیاری است (name/email از id_token هم می‌آید) — نبودش ورود را نمی‌شکند
        return {"_error": str(exc)}
