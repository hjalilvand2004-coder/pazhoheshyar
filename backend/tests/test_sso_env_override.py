"""آزمون نشانی‌های بازگشت SSO برای استقرار تولیدی — پورت 8088.

طبق سند ادغام پرتال، مسیر callback باید کاراکتربه‌کاراکتر با مقدار ثبت‌شده
در clients.json پرتال یکی باشد؛ این آزمون تضمین می‌کند (۱) تنظیمات اولیه
مطابق استقرار تولیدی http://188.212.96.235:8088 است و (۲) متغیرهای محیطی
SSO_REDIRECT_URI / SSO_POST_LOGOUT_REDIRECT_URI که یونیت systemd ست می‌کند
بر تنظیم پنل مدیریت اولویت دارند.
"""
import os
from unittest import mock

from app.core import sso_store
from app.core.database import SessionLocal
from app.core.sso_store import get_settings
from app.models import SsoSettings

REDIRECT_8088 = "http://188.212.96.235:8088/api/v1/auth/sso/callback"
LOGOUT_8088 = "http://188.212.96.235:8088/?loggedOut=1"
CLIENT_ID_PORTAL = "pajouhyar360"  # همان که در پنل مدیریت پرتال دانشجویار۳۶۰ ثبت شده


def _set_panel_values(redirect_uri: str, post_logout: str) -> None:
    """مقدار پنل مدیریت را عمداً به مقدار قدیمی/متفاوت می‌گذارد."""
    db = SessionLocal()
    try:
        row = db.get(SsoSettings, 1)
        if not row:
            row = SsoSettings(id=1, enabled=True)
            db.add(row)
        row.issuer = "http://portal.test"
        row.client_id = CLIENT_ID_PORTAL
        row.redirect_uri = redirect_uri
        row.post_logout_redirect_uri = post_logout
        db.commit()
    finally:
        db.close()


def test_initial_sso_matches_production_deployment():
    """تنظیمات اولیه باید دقیقاً مطابق استقرار تولیدی و ثبت پرتال باشد."""
    assert sso_store.INITIAL_SSO["client_id"] == CLIENT_ID_PORTAL
    assert sso_store.INITIAL_SSO["redirect_uri"] == REDIRECT_8088
    assert sso_store.INITIAL_SSO["post_logout_redirect_uri"] == LOGOUT_8088


def test_panel_setting_used_without_env():
    """بدون متغیر محیطی، مقدار ذخیره‌شدهٔ پنل معتبر است."""
    _set_panel_values("http://188.212.96.235:8000/sso/callback", "http://188.212.96.235:8000/?loggedOut=1")
    env = {k: "" for k in ("SSO_REDIRECT_URI", "SSO_POST_LOGOUT_REDIRECT_URI")}
    with mock.patch.dict(os.environ, env):
        db = SessionLocal()
        try:
            s = get_settings(db)
            assert s.redirect_uri == "http://188.212.96.235:8000/sso/callback"
            assert s.post_logout_redirect_uri == "http://188.212.96.235:8000/?loggedOut=1"
        finally:
            db.close()


def test_env_override_wins_over_panel_setting():
    """با متغیر محیطی استقرار، نشانی callback حتمی به مقدار 8088 قفل می‌شود."""
    _set_panel_values("http://188.212.96.235:8000/sso/callback", "http://188.212.96.235:8000/?loggedOut=1")
    env = {
        "SSO_CLIENT_ID": CLIENT_ID_PORTAL,
        "SSO_REDIRECT_URI": REDIRECT_8088,
        "SSO_POST_LOGOUT_REDIRECT_URI": LOGOUT_8088,
    }
    with mock.patch.dict(os.environ, env):
        db = SessionLocal()
        try:
            s = get_settings(db)
            assert s.client_id == CLIENT_ID_PORTAL
            assert s.redirect_uri == REDIRECT_8088
            assert s.post_logout_redirect_uri == LOGOUT_8088
        finally:
            db.close()
