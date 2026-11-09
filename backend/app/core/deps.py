"""وابستگی‌های احراز هویت و مجوزدهی — بررسی نقش‌ها همیشه در بک‌اند انجام می‌شود"""
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..models import User
from .config import SERVICE_TOKEN
from .database import get_db
from .security import decode_token


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="ورود انجام نشده است")
    payload = decode_token(auth.removeprefix("Bearer ").strip())
    if not payload:
        raise HTTPException(status_code=401, detail="نشست منقضی شده است؛ دوباره وارد شوید")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="کاربر یافت نشد یا غیرفعال است")
    request.state.user = user
    return user


def require_roles(*roles: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        if not set(user.roles or []) & set(roles):
            raise HTTPException(status_code=403, detail="دسترسی لازم برای این عملیات را ندارید")
        return user
    return checker


def manager_or_service(request: Request, user: User = Depends(get_current_user)) -> None:
    """دسترسی برای مدیر پژوهش/سامانه یا سامانه دیگر با توکن سرویس"""
    token = request.headers.get("X-Service-Token", "")
    if SERVICE_TOKEN and hmac_equal(token, SERVICE_TOKEN):
        return
    if set(user.roles or []) & {"research_manager", "system_admin"}:
        return
    raise HTTPException(status_code=403, detail="دسترسی مجاز نیست")


def hmac_equal(a: str, b: str) -> bool:
    import hmac as _h
    return _h.compare_digest(a or "", b or "")
