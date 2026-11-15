"""فایل آینهٔ تنظیمات SSO — درس‌آموختهٔ رسمی سند ادغام پرتال دانشجویار۳۶۰.

تنظیمات علاوه بر جدول sso_settings در «فایل آینه» (data/app_settings.json)
نوشته می‌شود؛ اگر دیتابیس تعویض/بازسازی شده باشد و ردیف تنظیمات نبود،
در نخستین خواندن از فایل آینه بازگردانده می‌شود (hydrate) و در نبود هر دو،
تنظیمات اولیهٔ پرتال ساخته می‌شود. سناریوی پذیرش ۱۰ سند با همین مکانیزم سبز می‌شود.
"""
import json
import os
from typing import Optional

from sqlalchemy.orm import Session

from .config import (
    DATA_DIR, SSO_PORTAL_CLIENT_ID, SSO_PORTAL_ISSUER,
)
from ..models import SsoSettings

MIRROR_FILE = DATA_DIR / "app_settings.json"

# تنظیمات اولیهٔ ورود یکپارچه بر اساس سند ادغام پرتال دانشجویار۳۶۰
# (redirect_uri باید با آدرس واقعی استقرار همین سامانه یکی و کاراکتربه‌کاراکتر
#  در clients.json پرتال ثبت شود — مدیر سامانه از پنل بازبینی می‌کند.)
INITIAL_SSO = {
    "enabled": True,
    "issuer": SSO_PORTAL_ISSUER,
    "client_id": SSO_PORTAL_CLIENT_ID,
    "client_type": "public",          # client عمومی + PKCE/S256 — بدون client_secret
    "client_secret": "",
    # مسیر callback باید دقیقاً با مسیر واقعی روتر (api/v1/auth/sso/callback) و
    # با مقدار ثبت‌شده در data/clients.json پرتال کاراکتربه‌کاراکتر یکی باشد.
    "redirect_uri": "http://188.212.96.235:8088/api/v1/auth/sso/callback",
    "post_logout_redirect_uri": "http://188.212.96.235:8088/?loggedOut=1",
    "button_label": "ورود با حساب پرتال دانشجویار۳۶۰",
    "scope": "openid profile email",
    "auto_create_users": True,
    "default_roles": ["student"],
}


def _mirror_read() -> Optional[dict]:
    try:
        return json.loads(MIRROR_FILE.read_text("utf-8"))
    except Exception:
        return None


def mirror_write(s: SsoSettings) -> None:
    """نوشتن فایل آینه کنار دیتابیس — پس از هر ذخیره در پنل مدیریت."""
    payload = {
        "sso": {
            "enabled": bool(s.enabled),
            "issuer": s.issuer or "",
            "client_id": s.client_id or "",
            "client_type": s.client_type or "public",
            "client_secret": s.client_secret or "",
            "redirect_uri": s.redirect_uri or "",
            "post_logout_redirect_uri": s.post_logout_redirect_uri or "",
            "button_label": s.button_label or "",
            "scope": s.scope or "openid profile email",
            "auto_create_users": bool(s.auto_create_users),
            "default_roles": s.default_roles or ["student"],
        }
    }
    try:
        MIRROR_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    except Exception:
        pass  # نبود اجازهٔ نوشتن نباید ورود را بشکند؛ تنظیمات در جدول هم هست


def _row_from_dict(db: Session, d: dict) -> SsoSettings:
    s = SsoSettings(id=1, **d)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _apply_env_overrides(s: SsoSettings) -> SsoSettings:
    """نشانی‌های بازگشتِ استقرار تولیدی را از متغیر محیطی حتمی می‌کند.

    در استقرار سرور (systemd/داکر) اگر SSO_CLIENT_ID یا SSO_REDIRECT_URI یا
    SSO_POST_LOGOUT_REDIRECT_URI ست شده باشند، بر مقدار پنل مدیریت اولویت
    دارند تا مقادیر جریان ورود همیشه با clients.json پرتال یکی بماند.
    اعمال فقط در حافظه است؛ با حذف متغیر، تنظیم پنل دوباره معتبر می‌شود.
    """
    env_client = os.environ.get("SSO_CLIENT_ID", "").strip()
    env_redirect = os.environ.get("SSO_REDIRECT_URI", "").strip()
    env_logout = os.environ.get("SSO_POST_LOGOUT_REDIRECT_URI", "").strip()
    if env_client:
        s.client_id = env_client
    if env_redirect:
        s.redirect_uri = env_redirect
    if env_logout:
        s.post_logout_redirect_uri = env_logout
    return s


def get_settings(db: Session) -> SsoSettings:
    """خواندن خودترمیم‌شونده: جدول ← فایل آینه ← تنظیمات اولیهٔ پرتال."""
    s = db.get(SsoSettings, 1)
    if s:
        return _apply_env_overrides(s)
    mirror = _mirror_read()
    if mirror and isinstance(mirror.get("sso"), dict):
        data = {k: v for k, v in mirror["sso"].items()
                if k in {c.name for c in SsoSettings.__table__.columns} - {"id", "updated_at"}}
        return _apply_env_overrides(_row_from_dict(db, data))
    return _apply_env_overrides(_row_from_dict(db, dict(INITIAL_SSO)))
