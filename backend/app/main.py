"""اپلیکیشن FastAPI پژوهشیار۳۶۰ — سرویس‌های مستقل + سرو فرانت React"""
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .core.config import APP_NAME, APP_VERSION, FRONTEND_DIST
from .core.database import SessionLocal, init_db
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
    if os.environ.get("SEED_ON_START", "1") == "1":
        db = SessionLocal()
        try:
            seed(db)
        finally:
            db.close()


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
