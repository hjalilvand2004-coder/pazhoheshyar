"""سرویس احراز هویت و ورود یکپارچه (SSO/OIDC) — پرتال دانشجویار۳۶۰

جریان: Authorization Code + PKCE (S256) برای client عمومی؛ state/nonce/
code_verifier در کوکی HttpOnly SameSite=Lax با عمر ~۱۰ دقیقه نگه داشته
می‌شود؛ تبادل کد و اعتبارسنجی id_token کاملاً در سمت سرور انجام می‌شود؛
خطاها همیشه به پیام فارسی خوانا نگاشت می‌شوند و با کد خطا و IP ثبت می‌شوند.
"""
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.config import (
    APP_NAME, APP_VERSION, SECRET_KEY, SSO_FLOW_COOKIE, SSO_FLOW_TTL_SECONDS, TOKEN_ALGORITHM,
)
from ..core.deps import get_current_user
from ..core.database import get_db
from ..core import oidc
from ..core.oidc import SsoError, error_message
from ..core.security import create_token, decode_token, verify_password
from ..core.sso_store import get_settings
from ..core.utils import log_event
from ..models import User
from ..serializers import ser_user

router = APIRouter(prefix="/api/v1/auth", tags=["احراز هویت"])


class LoginIn(BaseModel):
    username: str
    password: str


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else "") or (request.client.host if request.client else "?")


def _flow_cookie(payload: dict) -> str:
    """امضای محتوای جریان (state/nonce/verifier/link_uid) با JWT — دستکاری ناممکن می‌شود."""
    now = datetime.now(timezone.utc)
    return jwt.encode({**payload, "iat": now, "exp": now + timedelta(seconds=SSO_FLOW_TTL_SECONDS)},
                      SECRET_KEY, algorithm=TOKEN_ALGORITHM)


def _decode_flow(cookie_value: str) -> dict | None:
    try:
        return jwt.decode(cookie_value, SECRET_KEY, algorithms=[TOKEN_ALGORITHM])
    except jwt.PyJWTError:
        return None


def _set_flow_cookie(response: Response, value: str) -> None:
    response.set_cookie(
        SSO_FLOW_COOKIE, value, max_age=SSO_FLOW_TTL_SECONDS,
        httponly=True, samesite="lax", path="/api/v1/auth/sso",
    )


def _clear_flow_cookie(response: Response) -> None:
    response.delete_cookie(SSO_FLOW_COOKIE, path="/api/v1/auth/sso")


def _fail(db: Session, request: Request, code: str, status_code: int = 400):
    """ثبت رخداد خطا با کد و IP + پیام فارسی خوانا (بدون stack trace)."""
    log_event(db, "sso_error", None, {"code": code, "ip": _client_ip(request)})
    db.commit()
    raise HTTPException(status_code=status_code, detail=error_message(code))


def _portal_roles(claims: dict, client_id: str) -> list[str]:
    """نقش‌های client از claim resource_access — پسوند .admin یعنی مدیر سامانه."""
    raw = (claims.get("resource_access") or {}).get(client_id, {}).get("roles", []) or []
    if any(str(r).endswith(".admin") for r in raw):
        return ["system_admin"]
    return []


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


@router.post("/logout", summary="خروج — با ابطال نشست محلی و بازگشت به پرتال")
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """نشست محلی مستقل از نشست IdP باطل می‌شود؛ اگر SSO فعال باشد مسیر end_session پرتال هم برگردانده می‌شود."""
    out: dict = {"ok": True}
    s = get_settings(db)
    if s.enabled and (s.issuer or ""):
        try:
            pc = oidc.get_provider_config(s.issuer)
            ep = pc.get("end_session_endpoint")
            if ep and (s.post_logout_redirect_uri or ""):
                from urllib.parse import quote
                out["end_session_url"] = f"{ep}?post_logout_redirect_uri={quote(s.post_logout_redirect_uri)}"
        except SsoError:
            pass  # پرتال در دسترس نیست — خروجِ محلی کماکان انجام می‌شود
    return out


@router.get("/sso/config", summary="تنظیمات عمومی SSO برای صفحه ورود")
def sso_config(db: Session = Depends(get_db)):
    s = get_settings(db)
    if not s.enabled:
        return {"enabled": False, "message": "ورود یکپارچه هنوز فعال نشده است؛ از مدیر سامانه پیگیری کنید."}
    return {
        "enabled": True,
        "issuer": s.issuer,
        "client_id": s.client_id,
        "client_type": s.client_type or "public",
        "redirect_uri": s.redirect_uri,
        "scope": s.scope,
        "button_label": s.button_label or "ورود با حساب دانشگاهی (SSO)",
        "authorization_url": "/api/v1/auth/sso/login",
    }


@router.get("/sso/login", summary="شروع ورود یکپارچه — هدایت به پرتال با PKCE", response_class=RedirectResponse)
def sso_login(request: Request, token: str = "", db: Session = Depends(get_db)):
    """گام ۲ سند: تولید state/nonce/code_verifier، ذخیره در کوکی HttpOnly، ریدایرکت 302 به پرتال.

    اگر توکن محلی ارسال شود، پس از بازگشت، هویت SSO به همان حساب متصل می‌شود (اتصال حساب از پروفایل).
    """
    s = get_settings(db)
    if not s.enabled:
        log_event(db, "sso_error", None, {"code": "disabled", "ip": _client_ip(request)})
        db.commit()
        raise HTTPException(status_code=400, detail=error_message("disabled"))
    if not (s.issuer and s.client_id and s.redirect_uri):
        log_event(db, "sso_error", None, {"code": "config", "ip": _client_ip(request)})
        db.commit()
        raise HTTPException(status_code=400, detail=error_message("config"))

    link_uid = None
    if token:
        payload = decode_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="توکن نامعتبر یا منقضی است")
        link_uid = int(payload.get("sub") or 0) or None

    try:
        pc = oidc.get_provider_config(s.issuer)
    except SsoError as exc:
        _fail(db, request, exc.code)

    state = uuid.uuid4().hex          # ≥۳۲ کاراکتر
    nonce = uuid.uuid4().hex          # ≥۳۲ کاراکتر — یک‌بارمصرف (درون کوکی تک‌جریان)
    verifier, challenge = oidc.generate_pkce()
    flow_payload = {"state": state, "nonce": nonce, "verifier": verifier, "link_uid": link_uid}
    cookie_value = _flow_cookie(flow_payload)

    try:
        url = oidc.build_auth_url(pc, s.client_id, s.redirect_uri, s.scope, state,
                                  nonce=nonce, code_challenge=challenge)
    except SsoError as exc:
        _fail(db, request, exc.code)

    log_event(db, "sso_login_started", None, {"ip": _client_ip(request), "issuer": s.issuer})
    db.commit()
    response = RedirectResponse(url, status_code=302)
    _set_flow_cookie(response, cookie_value)
    return response


@router.get("/sso/callback", summary="بازگشت از پرتال — اعتبارسنجی کامل id_token و صدور نشست محلی")
def sso_callback(request: Request, code: str = "", state: str = "", error: str = "",
                 db: Session = Depends(get_db)):
    """گام‌های ۳ تا ۵ سند: تطابق state (کوکی)، تبادل کد با PKCE در سمت سرور،
    اعتبارسنجی RS256/iss/aud/nonce/exp/iat/sub، سپس پرووژنینگ حساب محلی."""
    s = get_settings(db)
    if not s.enabled:
        _fail(db, request, "disabled")

    if error:  # سرور هویت با پارامتر error بازگشته (مثلاً لغو توسط کاربر)
        _fail(db, request, "access_denied" if error == "access_denied" else "invalid_response")

    flow = _decode_flow(request.cookies.get(SSO_FLOW_COOKIE, ""))
    if not flow or not state or flow.get("state") != state:
        _fail(db, request, "state")

    try:
        pc = oidc.get_provider_config(s.issuer)
        # تبادل کد در سمت سرورِ سامانه — برای client عمومی بدون client_secret و با code_verifier
        tokens = oidc.exchange_code(pc, s.client_id,
                                    s.client_secret if (s.client_type or "public") == "confidential" else "",
                                    code, s.redirect_uri, code_verifier=flow.get("verifier", ""))
        id_token = tokens.get("id_token")
        if not id_token:
            raise SsoError("invalid_response", "id_token در پاسخ توکن نیست")
        claims = oidc.validate_id_token(
            id_token, issuer=s.issuer, client_id=s.client_id,
            expected_nonce=flow.get("nonce", ""), jwks_uri=pc.get("jwks_uri", ""),
        )
        userinfo = oidc.fetch_userinfo(pc, tokens.get("access_token", "")) or {}
    except SsoError as exc:
        _fail(db, request, exc.code)

    issuer = s.issuer.rstrip("/")
    sub = str(claims.get("sub", ""))
    preferred = str(userinfo.get("preferred_username") or claims.get("preferred_username") or "").strip()
    display_name = userinfo.get("name") or claims.get("name") or ""
    portal_roles = _portal_roles(claims, s.client_id)

    # ---------- حالت اتصال حساب: کاربرِ واردشده هویت SSO را به حساب محلی‌اش متصل می‌کند
    link_uid = flow.get("link_uid")
    if link_uid:
        user = db.get(User, link_uid)
        if not user:
            _fail(db, request, "invalid_response", 404)
        clash = db.query(User).filter(User.sso_issuer == issuer, User.sso_sub == sub, User.id != user.id).one_or_none()
        if clash:
            log_event(db, "sso_error", user.id, {"code": "identity_clash", "ip": _client_ip(request)})
            db.commit()
            raise HTTPException(status_code=409, detail="این هویت SSO قبلاً به حساب دیگری متصل شده است")
        user.sso_issuer, user.sso_sub = issuer, sub
        log_event(db, "user_sso_linked", user.id, {"issuer": issuer, "ip": _client_ip(request)})
        db.commit()
        token = create_token(user.id, user.username, user.roles or [])
        response = JSONResponse({"token": token, "user": ser_user(user), "linked": True})
        _clear_flow_cookie(response)
        return response

    # ---------- پرووژنینگ (ترتیب سند): ۱) sub ذخیره‌شده  ۲) username == preferred_username  ۳) ساخت خودکار
    user = db.query(User).filter(User.sso_issuer == issuer, User.sso_sub == sub).one_or_none()
    linked_by_username = False
    if not user and preferred:
        user = db.query(User).filter(User.username == preferred.lower()).one_or_none()
        linked_by_username = bool(user)

    if not user and s.auto_create_users:
        base = (preferred or userinfo.get("email") or claims.get("email") or f"sso-{sub[:12]}").lower().strip() or f"sso-{sub[:12]}"
        username = base
        if db.query(User).filter(User.username == username).one_or_none():
            username = f"{base}-{sub[:6]}"  # جلوگیری از تداخل نام کاربری
        user = User(
            username=username,
            display_name=display_name or username,
            roles=portal_roles or s.default_roles or ["student"],
            sso_issuer=issuer, sso_sub=sub,
        )
        db.add(user)
        db.flush()
        log_event(db, "user_sso_created", user.id,
                  {"username": username, "ip": _client_ip(request), "roles": user.roles})
        db.commit()
    if not user:
        _fail(db, request, "invalid_response", 403)

    if not user.is_active:
        raise HTTPException(status_code=403, detail="حساب شما غیرفعال است")

    if not user.sso_issuer:  # سناریوی ۵ سند: اتصال حساب موجود هم‌نام و ذخیرهٔ sub
        user.sso_issuer, user.sso_sub = issuer, sub
        if not (user.display_name or "").strip() and display_name:
            user.display_name = display_name
        log_event(db, "user_sso_linked", user.id,
                  {"issuer": issuer, "by": "username" if linked_by_username else "first_login", "ip": _client_ip(request)})

    token = create_token(user.id, user.username, user.roles or [])
    log_event(db, "user_login", user.id,
              {"method": "sso", "issuer": issuer, "ip": _client_ip(request)})
    db.commit()
    response = JSONResponse({"token": token, "user": ser_user(user)})
    _clear_flow_cookie(response)
    return response
