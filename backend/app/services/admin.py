"""سرویس مدیریت پژوهش و سامانه — شاخص‌ها، تنظیمات SSO، کاربران"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core import oidc
from ..core.oidc import error_message
from ..core.deps import require_roles
from ..core.database import get_db
from ..core.sso_store import get_settings, mirror_write
from ..core.utils import log_event
from ..models import (
    EventLog, Offer, Project, ResearchRequest, SsoSettings, User,
)
from ..serializers import ser_event, ser_user

router = APIRouter(prefix="/api/v1/admin", tags=["مدیریت"])


@router.get("/metrics", summary="شاخص‌های داشبورد مدیریت پژوهش")
def metrics(user: User = Depends(require_roles("research_manager", "system_admin")), db: Session = Depends(get_db)):
    from .. import state_machine as sm
    req_by_status = {s: 0 for s in sm.REQUEST_STATUSES}
    for status, count in db.query(ResearchRequest.status, __import__("sqlalchemy").func.count())\
            .group_by(ResearchRequest.status).all():
        req_by_status[status] = count
    return {
        "requests_by_status": req_by_status,
        "requests_total": sum(req_by_status.values()),
        "offers_total": db.query(Offer).count(),
        "offers_active": db.query(Offer).filter(Offer.status.in_(["sent", "viewed", "in_dialogue"])).count(),
        "projects_active": db.query(Project).filter(Project.status == "active").count(),
        "projects_closed": db.query(Project).filter(Project.status == "closed").count(),
        "users_total": db.query(User).count(),
        "students": db.query(User).filter(User.roles.contains("student")).count(),
        "professors": db.query(User).filter(User.roles.contains("professor")).count(),
    }


@router.get("/users", summary="فهرست کاربران (مدیران)")
def list_users(user: User = Depends(require_roles("research_manager", "system_admin")), db: Session = Depends(get_db)):
    return [ser_user(u) for u in db.query(User).order_by(User.id).limit(500).all()]


class RolesIn(BaseModel):
    roles: list[str]


@router.patch("/users/{user_id}/roles", summary="ویرایش نقش‌های کاربر (مدیر سامانه)")
def set_roles(user_id: int, body: RolesIn,
              user: User = Depends(require_roles("system_admin")), db: Session = Depends(get_db)):
    valid = {"student", "professor", "research_manager", "system_admin"}
    if not set(body.roles) <= valid:
        raise HTTPException(status_code=400, detail="نقش نامعتبر است")
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="کاربر یافت نشد")
    target.roles = body.roles
    log_event(db, "user_roles_changed", user.id, {"target": user_id, "roles": body.roles})
    db.commit()
    return ser_user(target)


class SsoIn(BaseModel):
    enabled: bool = False
    issuer: str = ""
    client_id: str = ""
    client_type: str = "public"          # public (PKCE/S256، بدون secret) یا confidential
    client_secret: str = ""              # فقط برای confidential — خالی = بدون تغییر
    redirect_uri: str = ""
    post_logout_redirect_uri: str = ""
    button_label: str = ""
    scope: str = "openid profile email"
    auto_create_users: bool = False
    default_roles: list[str] = ["student"]


def _get_sso(db: Session) -> SsoSettings:
    return get_settings(db)  # خودترمیم‌شونده: جدول ← فایل آینه ← تنظیمات اولیهٔ پرتال


@router.get("/sso/settings", summary="تنظیمات ورود یکپارچه")
def get_sso(user: User = Depends(require_roles("system_admin")), db: Session = Depends(get_db)):
    s = _get_sso(db)
    return {
        "enabled": s.enabled, "issuer": s.issuer, "client_id": s.client_id,
        "client_type": s.client_type or "public",
        "client_secret_set": bool(s.client_secret), "redirect_uri": s.redirect_uri,
        "post_logout_redirect_uri": s.post_logout_redirect_uri or "",
        "button_label": s.button_label or "",
        "scope": s.scope, "auto_create_users": s.auto_create_users,
        "default_roles": s.default_roles or ["student"],
        "last_test_status": s.last_test_status,
    }


@router.put("/sso/settings", summary="ذخیره تنظیمات ورود یکپارچه (پرتال دانشجویار۳۶۰ / Keycloak)")
def put_sso(body: SsoIn, user: User = Depends(require_roles("system_admin")), db: Session = Depends(get_db)):
    if body.enabled and not (body.issuer.strip() and body.client_id.strip() and body.redirect_uri.strip()):
        raise HTTPException(
            status_code=400,
            detail="برای فعال‌سازی SSO، هر سه مقدار Issuer و Client ID و Redirect URI الزامی است",
        )
    if body.client_type not in ("public", "confidential"):
        raise HTTPException(status_code=400, detail="نوع کلاینت باید public یا confidential باشد")
    s = _get_sso(db)
    s.enabled = body.enabled
    s.issuer = body.issuer.strip().rstrip("/")
    s.client_id = body.client_id.strip()
    s.client_type = body.client_type
    s.redirect_uri = body.redirect_uri.strip()
    s.post_logout_redirect_uri = body.post_logout_redirect_uri.strip()
    s.button_label = body.button_label.strip()
    s.scope = body.scope
    s.auto_create_users = body.auto_create_users
    s.default_roles = body.default_roles
    if body.client_secret:  # خالی = بدون تغییر
        s.client_secret = body.client_secret
    log_event(db, "sso_settings_updated", user.id,
              {"enabled": body.enabled, "issuer": s.issuer, "client_type": s.client_type})
    db.commit()
    mirror_write(s)  # فایل آینهٔ پایدار — سناریوی پذیرش ۱۰ سند
    return get_sso(user, db)


@router.post("/sso/test", summary="تست اتصال به پرتال (Discovery + JWKS)")
def test_sso(user: User = Depends(require_roles("system_admin")), db: Session = Depends(get_db)):
    """Discovery و JWKS با HTTP واقعی واکشی می‌شود؛ انطباق issuer و تعداد کلیدها گزارش می‌شود."""
    s = _get_sso(db)
    result: dict = {"ok": False, "message": "", "provider": None, "jwks_keys": 0}
    try:
        pc = oidc.get_provider_config(s.issuer)
        missing = [k for k in ("authorization_endpoint", "token_endpoint", "userinfo_endpoint") if not pc.get(k)]
        keys = []
        try:
            keys = oidc.get_jwks(pc.get("jwks_uri", "")).get("keys", [])
        except oidc.SsoError as exc:
            if exc.code != "config":
                raise
        result["jwks_keys"] = len(keys)
        result["provider"] = {
            "issuer_reported": pc.get("issuer"),
            "authorization_endpoint": pc.get("authorization_endpoint"),
            "token_endpoint": pc.get("token_endpoint"),
            "userinfo_endpoint": pc.get("userinfo_endpoint"),
            "jwks_uri": pc.get("jwks_uri"),
            "end_session_endpoint": pc.get("end_session_endpoint"),
        }
        issuer_ok = bool(pc.get("issuer")) and pc["issuer"].rstrip("/") == (s.issuer or "").rstrip("/")
        if missing:
            msg = f"پاسخ Discovery ناقص است؛ این موارد یافت نشد: {', '.join(missing)}"
        elif not keys:
            msg = "JWKS خالی است؛ کلید امضای RS256 برای اعتبارسنجی id_token در دسترس نیست."
        elif not issuer_ok:
            msg = f"هشدار: Issuer اعلام‌شده توسط سرور ({pc.get('issuer')}) با مقدار تنظیم‌شده ({s.issuer}) یکسان نیست."
            result["ok"] = True  # اتصال برقرار است اما پیکربندی باید بازبینی شود
        else:
            msg = f"اتصال موفق بود؛ Discovery کامل، Issuer منطبق و JWKS با {len(keys)} کلید RS256 خوانده شد."
            result["ok"] = True
    except oidc.SsoError as exc:
        msg = error_message(exc.code) + (f" [{exc.detail[:120]}]" if exc.detail else "")
    s.last_test_status = msg
    result["message"] = msg
    db.commit()
    return result
