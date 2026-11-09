"""فهرست قابلیت‌های سرویس‌محور سامانه — برای سامانه‌های دیگر اکوسیستم دانشجو۳۶۰"""
from fastapi import APIRouter

from ..core.config import APP_NAME, APP_VERSION

router = APIRouter(prefix="/api/v1/services", tags=["فهرست سرویس‌ها"])

SERVICES = [
    {"module": "auth", "title": "احراز هویت و SSO",
     "description": "ورود محلی + ورود یکپارچه Keycloak/OIDC با اتصال issuer+sub",
     "endpoints": ["POST /api/v1/auth/login", "GET /api/v1/auth/me", "GET /api/v1/auth/sso/config",
                   "GET /api/v1/auth/sso/login", "GET /api/v1/auth/sso/callback"]},
    {"module": "profiles", "title": "پروفایل پژوهشی",
     "description": "پروفایل دانشجو/استاد با تفکیک فیلدهای حساس",
     "endpoints": ["GET /api/v1/profiles/me", "PUT /api/v1/profiles/me", "GET /api/v1/profiles/professors",
                   "GET /api/v1/profiles/{user_id}"]},
    {"module": "topics", "title": "بانک موضوعات و الگوها",
     "description": "انتشار موضوع/الگوی استاندارد توسط استاد و استفاده دانشجو",
     "endpoints": ["GET /api/v1/topics", "POST /api/v1/topics", "PUT /api/v1/topics/{id}", "DELETE /api/v1/topics/{id}"]},
    {"module": "requests", "title": "درخواست پژوهش",
     "description": "ثبت، استخر پژوهشی، ماشین وضعیت، محرمانگی، تأیید دانشگاه",
     "endpoints": ["POST /api/v1/requests", "GET /api/v1/requests/mine", "GET /api/v1/requests/pool",
                   "GET /api/v1/requests/{id}", "PATCH /api/v1/requests/{id}", "POST /api/v1/requests/{id}/status",
                   "POST /api/v1/requests/{id}/share-secret", "POST /api/v1/requests/{id}/attachments",
                   "GET /api/v1/requests/{id}/offers", "POST /api/v1/requests/{id}/approve"]},
    {"module": "offers", "title": "اعلام آمادگی و تأیید دوطرفه",
     "description": "اعلام آمادگی استاد، پذیرش/رد دانشجو با قفل اتمی",
     "endpoints": ["POST /api/v1/requests/{id}/offers", "GET /api/v1/offers/mine",
                   "POST /api/v1/offers/{id}/start-dialogue", "POST /api/v1/offers/{id}/accept",
                   "POST /api/v1/offers/{id}/reject", "POST /api/v1/offers/{id}/withdraw"]},
    {"module": "conversations", "title": "گفت‌وگو",
     "description": "پیام متنی/فایل، درخواست جلسه، گزارش سوءاستفاده",
     "endpoints": ["POST /api/v1/conversations/by-request/{rid}/with/{pid}", "GET /api/v1/conversations/mine",
                   "GET /api/v1/conversations/{id}/messages", "POST /api/v1/conversations/{id}/messages",
                   "POST /api/v1/conversations/{id}/report"]},
    {"module": "agreements", "title": "توافق‌نامه همکاری",
     "description": "ویرایش و امضای دوطرفه؛ پس از امضا پروژه تشکیل یا پرونده به تأیید دانشگاه می‌رود",
     "endpoints": ["GET /api/v1/agreements/{id}", "PUT /api/v1/agreements/{id}",
                   "POST /api/v1/agreements/{id}/sign", "GET /api/v1/agreements/by-request/{rid}"]},
    {"module": "projects", "title": "مدیریت پروژه",
     "description": "اعضا، وظایف، جلسات، فایل‌ها، پیشرفت و خاتمه",
     "endpoints": ["GET /api/v1/projects/mine", "GET /api/v1/projects/{id}", "POST /api/v1/projects/{id}/members",
                   "POST /api/v1/projects/{id}/tasks", "PATCH /api/v1/projects/{id}/tasks/{tid}",
                   "POST /api/v1/projects/{id}/meetings", "POST /api/v1/projects/{id}/files",
                   "POST /api/v1/projects/{id}/progress", "POST /api/v1/projects/{id}/close"]},
    {"module": "files", "title": "فایل امن", "description": "دانلود با کنترل دسترسی و نام ذخیره غیرقابل حدس",
     "endpoints": ["GET /api/v1/files/{id}"]},
    {"module": "notifications", "title": "اعلان‌ها", "description": "اعلان داخلی کاربران",
     "endpoints": ["GET /api/v1/notifications", "GET /api/v1/notifications/count",
                   "POST /api/v1/notifications/{id}/read", "POST /api/v1/notifications/read-all"]},
    {"module": "events", "title": "جریان رخدادها",
     "description": "برای اعلان/تحلیل سامانه‌های دیگر — با X-Service-Token یا نقش مدیر",
     "endpoints": ["GET /api/v1/events"]},
    {"module": "ai", "title": "دستیار هوشمند پژوهش",
     "description": "تطبیق، پیشنهاد موضوع، تحلیل استعداد، پایش پیشرفت — قاعده‌محور و آزمایشی",
     "endpoints": ["GET /api/v1/ai/match-professors/{rid}", "POST /api/v1/ai/topic-suggestions",
                   "GET /api/v1/ai/talent-analysis", "POST /api/v1/ai/request-assistant",
                   "GET /api/v1/ai/progress-monitor/{pid}", "GET /api/v1/ai/journals", "GET /api/v1/ai/grants",
                   "POST /api/v1/ai/predict-acceptance"]},
    {"module": "admin", "title": "مدیریت", "description": "شاخص‌ها، کاربران، تنظیمات SSO",
     "endpoints": ["GET /api/v1/admin/metrics", "GET /api/v1/admin/users", "PATCH /api/v1/admin/users/{id}/roles",
                   "GET/PUT /api/v1/admin/sso/settings", "POST /api/v1/admin/sso/test"]},
]


@router.get("", summary="فهرست سرویس‌های ارائه‌شده به سایر سامانه‌ها")
def services():
    return {"app": APP_NAME, "version": APP_VERSION,
            "openapi_url": "/openapi.json", "docs_url": "/docs",
            "service_auth": "Bearer (توکن کاربر) یا X-Service-Token (سامانه‌به‌سامانه)",
            "services": SERVICES}


@router.get("/health", summary="سلامت سرویس")
def health():
    return {"status": "ok", "app": APP_NAME, "version": APP_VERSION}
