"""سرویس پروفایل پژوهشی دانشجو و استاد — فیلدهای حساس فقط برای صاحب و مدیران"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, require_roles
from ..core.database import get_db
from ..models import ResearchProfile, User
from ..serializers import ROLE_LABELS, ser_profile, ser_user

router = APIRouter(prefix="/api/v1/profiles", tags=["پروفایل پژوهشی"])


class ProfileIn(BaseModel):
    field_of_study: str = ""
    faculty_name: str = ""
    degree: str = ""
    interests: list[str] = []
    skills: list[str] = []
    bio: str = ""
    research_history: str = ""
    publications: list[str] = []
    availability: str = ""
    collaboration_type: str = ""
    research_goal: str = ""
    expertise: list[str] = []
    methods_tools: str = ""
    capacity: int = 0
    conditions: str = ""


def _get_or_create(db: Session, user_id: int) -> ResearchProfile:
    p = db.query(ResearchProfile).filter(ResearchProfile.user_id == user_id).one_or_none()
    if not p:
        p = ResearchProfile(user_id=user_id)
        db.add(p)
        db.commit()
        db.refresh(p)
    return p


@router.get("/me", summary="پروفایل من (کامل)")
def my_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ser_profile(_get_or_create(db, user.id), full=True)


@router.put("/me", summary="به‌روزرسانی پروفایل من")
def update_profile(body: ProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _get_or_create(db, user.id)
    for key, value in body.model_dump().items():
        setattr(p, key, value)
    db.commit()
    return ser_profile(p, full=True)


@router.get("/professors", summary="فهرست اساتید (نمای عمومی، بدون اطلاعات حساس)")
def professors(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(ResearchProfile, User)
        .join(User, User.id == ResearchProfile.user_id)
        .filter(User.roles.contains("professor"), User.is_active.is_(True))
        .all()
    )
    out = []
    for p, u in rows:
        d = ser_profile(p)
        d["display_name"] = u.display_name
        out.append(d)
    return out


@router.get("/{user_id}", summary="نمای عمومی پروفایل — سوابق کامل دانشجو نمایش داده نمی‌شود")
def public_profile(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if not target or not target.is_active:
        raise HTTPException(status_code=404, detail="کاربر یافت نشد")
    is_self = user.id == target.id
    is_manager = bool(set(user.roles or []) & {"research_manager", "system_admin"})
    p = _get_or_create(db, target.id)
    return {
        "user": ser_user(target),
        "profile": ser_profile(p, full=is_self or is_manager),
        "sensitive_hidden": not (is_self or is_manager),
    }
