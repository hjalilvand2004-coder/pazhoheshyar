"""سرویس مدیریت پژوهش و سامانه — شاخص‌ها، تنظیمات SSO، کاربران"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core import oidc
from ..core.deps import require_roles
from ..core.database import get_db
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
    client_secret: str = ""
    redirect_uri: str = ""
    scope: str = "openid profile email"
    auto_create_users: bool = False
    default_roles: list[str] = ["student"]


def _get_sso(db: Session) -> SsoSettings:
    s = db.get(SsoSettings, 1)
    if not s:
        s = SsoSettings(id=1)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


@router.get("/sso/settings", summary="تنظیمات ورود یکپارچه")
def get_sso(user: User = Depends(require_roles("system_admin")), db: Session = Depends(get_db)):
    s = _get_sso(db)
    return {
        "enabled": s.enabled, "issuer": s.issuer, "client_id": s.client_id,
        "client_secret_set": bool(s.client_secret), "redirect_uri": s.redirect_uri,
        "scope": s.scope, "auto_create_users": s.auto_create_users,
        "default_roles": s.default_roles or ["student"],
        "last_test_status": s.last_test_status,
    }


@router.put("/sso/settings", summary="ذخیره تنظیمات ورود یکپارچه (Keycloak/OIDC)")
def put_sso(body: SsoIn, user: User = Depends(require_roles("system_admin")), db: Session = Depends(get_db)):
    s = _get_sso(db)
    s.enabled = body.enabled
    s.issuer = body.issuer.strip().rstrip("/")
    s.client_id = body.client_id
    s.redirect_uri = body.redirect_uri
    s.scope = body.scope
    s.auto_create_users = body.auto_create_users
    s.default_roles = body.default_roles
    if body.client_secret:  # خالی = بدون تغییر
        s.client_secret = body.client_secret
    log_event(db, "sso_settings_updated", user.id, {"enabled": body.enabled, "issuer": s.issuer})
    db.commit()
    return get_sso(user, db)


@router.post("/sso/test", summary="تست اتصال به سرور هویت")
def test_sso(user: User = Depends(require_roles("system_admin")), db: Session = Depends(get_db)):
    s = _get_sso(db)
    try:
        pc = oidc.get_provider_config(s.issuer)
        ok = bool(pc.get("authorization_endpoint") and pc.get("token_endpoint"))
        msg = "اتصال موفق: تنظیمات OIDC سرور هویت خوانده شد." if ok else "پاسخ سرور کامل نیست."
    except oidc.SsoError as exc:
        ok, msg = False, str(exc)
    s.last_test_status = msg
    db.commit()
    return {"ok": ok, "message": msg}
