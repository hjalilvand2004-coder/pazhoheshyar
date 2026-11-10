"""فایل آینهٔ تنظیمات SSO — درس‌آموختهٔ رسمی سند ادغام پرتال دانشجویار۳۶۰.

تنظیمات علاوه بر جدول sso_settings در «فایل آینه» (data/app_settings.json)
نوشته می‌شود؛ اگر دیتابیس تعویض/بازسازی شده باشد و ردیف تنظیمات نبود،
در نخستین خواندن از فایل آینه بازگردانده می‌شود (hydrate) و در نبود هر دو،
تنظیمات اولیهٔ پرتال ساخته می‌شود. سناریوی پذیرش ۱۰ سند با همین مکانیزم سبز می‌شود.
"""
import json
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
    "redirect_uri": "http://188.212.96.235:8000/sso/callback",
    "post_logout_redirect_uri": "http://188.212.96.235:8000/?loggedOut=1",
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


def get_settings(db: Session) -> SsoSettings:
    """خواندن خودترمیم‌شونده: جدول ← فایل آینه ← تنظیمات اولیهٔ پرتال."""
    s = db.get(SsoSettings, 1)
    if s:
        return s
    mirror = _mirror_read()
    if mirror and isinstance(mirror.get("sso"), dict):
        data = {k: v for k, v in mirror["sso"].items()
                if k in {c.name for c in SsoSettings.__table__.columns} - {"id", "updated_at"}}
        return _row_from_dict(db, data)
    return _row_from_dict(db, dict(INITIAL_SSO))
