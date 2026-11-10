"""اپلیکیشن FastAPI پژوهشیار۳۶۰ — سرویس‌های مستقل + سرو فرانت React"""
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .core.config import APP_NAME, APP_VERSION, FRONTEND_DIST
from .core.database import SessionLocal, init_db
from .models import SsoSettings
from .seed import seed

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="سامانه هوشمند پژوهشیار۳۶۰ — بازار اتصال پژوهشی دانشجو و استاد (عضو اکوسیستم دانشجو۳۶۰). "
                "همه سرویس‌ها مستند و قابل استفاده توسط سامانه‌های دیگر است.",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000", "http://127.0.0.1:5173"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

from .services.agreements import router as agreements_router  # noqa: E402
from .services.ai import router as ai_router                  # noqa: E402
from .services.admin import router as admin_router            # noqa: E402
from .services.auth import router as auth_router              # noqa: E402
from .services.conversations import router as conv_router     # noqa: E402
from .services.events import router as events_router          # noqa: E402
from .services.files import router as files_router            # noqa: E402
from .services.notifications import router as notif_router    # noqa: E402
from .services.offers import router as offers_router          # noqa: E402
from .services.profiles import router as profiles_router      # noqa: E402
from .services.projects import router as projects_router      # noqa: E402
from .services.registry import router as registry_router      # noqa: E402
from .services.requests import router as requests_router      # noqa: E402
from .services.topics import router as topics_router          # noqa: E402

app.include_router(auth_router)
app.include_router(profiles_router)
app.include_router(topics_router)
app.include_router(requests_router)
app.include_router(offers_router)
app.include_router(conv_router)
app.include_router(agreements_router)
app.include_router(projects_router)
app.include_router(files_router)
app.include_router(notif_router)
app.include_router(events_router)
app.include_router(ai_router)
app.include_router(admin_router)
app.include_router(registry_router)


@app.on_event("startup")
def startup():
    init_db()
    _migrate_sso_columns()
    _upgrade_placeholder_sso()
    if os.environ.get("SEED_ON_START", "1") == "1":
        db = SessionLocal()
        try:
            seed(db)
        finally:
            db.close()


def _upgrade_placeholder_sso():
    """ارتقای یک‌بارهٔ تنظیمات قدیمی placeholder به پیکربندی پرتال دانشجویار۳۶۰."""
    try:
        from .core.sso_store import INITIAL_SSO, mirror_write
        db = SessionLocal()
        try:
            row = db.get(SsoSettings, 1)
            if row and "example" in (row.issuer or ""):  # مقدار نمونهٔ قدیمی — هرگز کار نکرده است
                for k, v in INITIAL_SSO.items():
                    setattr(row, k, v)
                db.commit()
                mirror_write(row)
        finally:
            db.close()
    except Exception:
        pass


def _migrate_sso_columns():
    """افزودن ستون‌های جدید SSO به دیتابیس‌های قدیمی‌تر (بدون از دست رفتن داده)."""
    from sqlalchemy import text
    from .core.database import engine
    new_cols = [
        ("client_type", "VARCHAR(20) DEFAULT 'confidential' NOT NULL"),
        ("post_logout_redirect_uri", "VARCHAR(400) DEFAULT '' NOT NULL"),
        ("button_label", "VARCHAR(120) DEFAULT '' NOT NULL"),
    ]
    try:
        with engine.begin() as conn:
            existing = {row[1] for row in conn.execute(text("PRAGMA table_info(sso_settings)"))}
            if existing:  # جدول موجود است
                for name, ddl in new_cols:
                    if name not in existing:
                        conn.execute(text(f"ALTER TABLE sso_settings ADD COLUMN {name} {ddl}"))
    except Exception:
        pass  # دیتابیس تازه ساخته می‌شود / موتور غیر SQLite — create_all ستون‌ها را دارد


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)


# ---------- سرو فرانت React (SPA) ----------
if (FRONTEND_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith(("api/", "docs", "openapi.json")):
            raise HTTPException(status_code=404, detail="یافت نشد")
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
