"""تنظیمات مرکزی پژوهشیار۳۶۰ — هم در حالت سورس و هم در بسته اجرایی (PyInstaller) کار می‌کند"""
import os
import secrets
import sys
from pathlib import Path


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


# ریشه پروژه / منابع بسته‌شده
if _is_frozen():
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    BASE_DIR = Path(sys.executable).parent  # پوشه کنار فایل اجرایی
else:
    RESOURCE_DIR = Path(__file__).resolve().parents[2]  # backend/
    BASE_DIR = RESOURCE_DIR.parent  # ریشه مخزن

DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", BASE_DIR / "uploads"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_DATABASE_URL_ENV = os.environ.get("DATABASE_URL", "")
# فقط نشانی‌های معتبر پایگاه‌داده پذیرفته می‌شود؛ مقادیر ناشناخته (مثل file:) نادیده گرفته می‌شوند
if not _DATABASE_URL_ENV.startswith(("sqlite", "postgresql", "mysql")):
    _DATABASE_URL_ENV = ""
DATABASE_URL = _DATABASE_URL_ENV or f"sqlite:///{DATA_DIR / 'pazhoheshyar.db'}"

# فرانت ساخته‌شده: در بسته اجرایی کنار منابع، در حالت سورس داخل frontend/dist
FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST", "")) if os.environ.get("FRONTEND_DIST") else (
    RESOURCE_DIR / "frontend_dist" if _is_frozen() else BASE_DIR / "frontend" / "dist"
)

# کلید امضای توکن: از متغیر محیطی، یا فایل پایدار کنار داده‌ها (تا با ری‌استارت، نشست‌ها معتبر بمانند)
SECRET_KEY_FILE = DATA_DIR / ".secret"
if os.environ.get("SECRET_KEY"):
    SECRET_KEY = os.environ["SECRET_KEY"]
else:
    if SECRET_KEY_FILE.exists():
        SECRET_KEY = SECRET_KEY_FILE.read_text().strip()
    else:
        SECRET_KEY = secrets.token_urlsafe(48)
        SECRET_KEY_FILE.write_text(SECRET_KEY)

TOKEN_ALGORITHM = "HS256"
TOKEN_TTL_HOURS = int(os.environ.get("TOKEN_TTL_HOURS", "12"))

# توکن سرویس‌به‌سرویس برای سامانه‌های دیگر اکوسیستم دانشجو۳۶۰ (اختیاری)
SERVICE_TOKEN = os.environ.get("SERVICE_TOKEN", "")

# محدودیت‌های ضداسپم
REQUEST_DAILY_LIMIT = int(os.environ.get("REQUEST_DAILY_LIMIT", "10"))
MESSAGE_HOURLY_LIMIT = int(os.environ.get("MESSAGE_HOURLY_LIMIT", "60"))
OFFER_DAILY_LIMIT = int(os.environ.get("OFFER_DAILY_LIMIT", "20"))

SEED_ON_START = os.environ.get("SEED_ON_START", "1") == "1"

APP_NAME = "پژوهشیار۳۶۰"
APP_VERSION = "1.0.0"
SSO_ISSUER_LABEL = "daneshjoo360-sso"

# ------------------------------------------------ پرتال ورود یکپارچهٔ دانشجویار۳۶۰ (طبق سند ادغام رسمی)
# این مقادیر «تنظیمات اولیه» هستند؛ مدیر سامانه از پنل مدیریت می‌تواند تغییرشان دهد.
SSO_PORTAL_ISSUER = "http://188.212.96.235:8086"     # دقیقاً و بدون اسلش انتهایی
SSO_PORTAL_CLIENT_ID = "pazhoheshyar360"             # باید در data/clients.json پرتال ثبت شود
SSO_FLOW_COOKIE = "py_sso_flow"                      # کوکی HttpOnly حامل state/nonce/code_verifier
SSO_FLOW_TTL_SECONDS = 600                           # ~۱۰ دقیقه
SSO_JWKS_CACHE_SECONDS = 3600                        # کش JWKS حداکثر ۱ ساعت (چرخش کلید بی‌دردسر)
