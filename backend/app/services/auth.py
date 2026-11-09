"""سرویس احراز هویت و ورود یکپارچه (SSO/OIDC)"""
import secrets
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.config import APP_NAME, APP_VERSION
from ..core.deps import get_current_user
from ..core.database import get_db
from ..core import oidc
from ..core.security import create_token, decode_token, verify_password
from ..core.utils import log_event
from ..models import SsoSettings, User
from ..serializers import ser_user

router = APIRouter(prefix="/api/v1/auth", tags=["احراز هویت"])

# وضعیت‌های موقت SSO (کوتاه‌عمر، در حافظه): state -> {"ts": زمان ساخت, "link_uid": شناسه کاربر برای اتصال حساب}
_sso_states: dict[str, dict] = {}
_SSO_STATE_TTL = 600  # ۱۰ دقیقه


def _purge_states() -> None:
    now = time.time()
    for k in [k for k, v in _sso_states.items() if now - v["ts"] > _SSO_STATE_TTL]:
        _sso_states.pop(k, None)


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login", summary="ورود با نام کاربری و رمز عبور")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username.strip().lower()).one_or_none()
    if not user or not user.is_active or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="نام کاربری یا رمز عبور نادرست است")
    token = create_token(user.id, user.username, user.roles or [])
    log_event(db, "user_login", user.id, {"method": "password"})
    db.commit()
    return {"token": token, "user": ser_user(user), "app": {"name": APP_NAME, "version": APP_VERSION}}


@router.get("/me", summary="کاربر جاری")
def me(user: User = Depends(get_current_user)):
    return ser_user(user)


@router.post("/logout", summary="خروج")
def logout(user: User = Depends(get_current_user)):
    return {"ok": True}


@router.get("/sso/config", summary="تنظیمات عمومی SSO برای صفحه ورود")
def sso_config(db: Session = Depends(get_db)):
    s = db.get(SsoSettings, 1)
    if not s or not s.enabled:
        return {"enabled": False, "message": "ورود یکپارچه هنوز فعال نشده است؛ از مدیر سامانه پیگیری کنید."}
    return {
        "enabled": True,
        "issuer": s.issuer,
        "client_id": s.client_id,
        "redirect_uri": s.redirect_uri,
        "scope": s.scope,
        "authorization_url": "/api/v1/auth/sso/login",
    }


@router.get("/sso/login", summary="شروع ورود یکپارچه — هدایت به سرور هویت", response_class=RedirectResponse)
def sso_login(token: str = "", db: Session = Depends(get_db)):
    """اگر توکن محلی ارسال شود، پس از بازگشت از سرور هویت، هویت SSO به همان حساب متصل می‌شود."""
    s = db.get(SsoSettings, 1)
    if not s or not s.enabled:
        raise HTTPException(status_code=400, detail="ورود یکپارچه غیرفعال است؛ مدیر سامانه باید از پنل مدیریت آن را فعال کند.")
    link_uid = None
    if token:
        payload = decode_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="توکن نامعتبر یا منقضی است")
        link_uid = int(payload.get("sub") or 0) or None
    _purge_states()
    state = uuid.uuid4().hex
    _sso_states[state] = {"ts": time.time(), "link_uid": link_uid}
    pc = oidc.get_provider_config(s.issuer)
    url = oidc.build_auth_url(pc, s.client_id, s.redirect_uri, s.scope, state)
    return RedirectResponse(url, status_code=302)


@router.get("/sso/callback", summary="بازگشت از سرور هویت — صدور نشست محلی")
def sso_callback(code: str = "", state: str = "", db: Session = Depends(get_db)):
    s = db.get(SsoSettings, 1)
    if not s or not s.enabled:
        raise HTTPException(status_code=400, detail="ورود یکپارچه غیرفعال است")
    record = _sso_states.pop(state, None)
    if not record or time.time() - record["ts"] > _SSO_STATE_TTL:
        raise HTTPException(status_code=400, detail="وضعیت SSO نامعتبر یا منقضی است؛ دوباره تلاش کنید")

    pc = oidc.get_provider_config(s.issuer)
    tokens = oidc.exchange_code(pc, s.client_id, s.client_secret, code, s.redirect_uri)
    userinfo = oidc.fetch_userinfo(pc, tokens.get("access_token", ""))

    issuer = s.issuer.rstrip("/")
    sub = str(userinfo.get("sub", ""))
    if not sub:
        raise HTTPException(status_code=400, detail="شناسه یکتای کاربر (sub) در پاسخ SSO یافت نشد")

    # حالت اتصال حساب: کاربرِ واردشده، هویت SSO خود را به حساب محلی‌اش متصل می‌کند
    link_uid = record.get("link_uid")
    if link_uid:
        user = db.get(User, link_uid)
        if not user:
            raise HTTPException(status_code=404, detail="حساب محلی برای اتصال یافت نشد")
        clash = db.query(User).filter(User.sso_issuer == issuer, User.sso_sub == sub, User.id != user.id).one_or_none()
        if clash:
            raise HTTPException(status_code=409, detail="این هویت SSO قبلاً به حساب دیگری متصل شده است")
        user.sso_issuer, user.sso_sub = issuer, sub
        log_event(db, "user_sso_linked", user.id, {"issuer": issuer})
        db.commit()
        token = create_token(user.id, user.username, user.roles or [])
        return {"token": token, "user": ser_user(user), "linked": True}

    # ورود معمولی SSO — اتصال هویت مرکزی با issuer + sub به حساب محلی
    user = db.query(User).filter(User.sso_issuer == issuer, User.sso_sub == sub).one_or_none()
    if not user and s.auto_create_users:
        base = str(userinfo.get("preferred_username") or userinfo.get("email") or f"sso-{sub[:12]}").lower().strip() or f"sso-{sub[:12]}"
        username = base
        if db.query(User).filter(User.username == username).one_or_none():
            username = f"{base}-{sub[:6]}"  # جلوگیری از تداخل نام کاربری
        user = User(
            username=username,
            display_name=userinfo.get("name") or username,
            roles=s.default_roles or ["student"],
            sso_issuer=issuer, sso_sub=sub,
        )
        db.add(user)
        db.flush()
        log_event(db, "user_sso_created", user.id, {"username": username})
        db.commit()
    if not user:
        raise HTTPException(
            status_code=403,
            detail="حساب SSO شما به هیچ حسابی در پژوهشیار۳۶۰ متصل نیست. ابتدا با نام کاربری وارد شوید یا از مدیر بخواهید حساب شما را متصل کند.",
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="حساب شما غیرفعال است")

    if not user.sso_issuer:  # اتصال حساب موجود به هویت SSO
        user.sso_issuer, user.sso_sub = issuer, sub
        db.commit()

    token = create_token(user.id, user.username, user.roles or [])
    log_event(db, "user_login", user.id, {"method": "sso", "issuer": issuer})
    db.commit()
    return {"token": token, "user": ser_user(user)}


def new_state() -> str:
    return secrets.token_urlsafe(24)
