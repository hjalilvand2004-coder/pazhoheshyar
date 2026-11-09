"""سرویس توافق‌نامه همکاری — ویرایش پیش از امضا، امضای دوطرفه، ارجاع به تأیید دانشگاه"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.deps import get_current_user
from ..core.database import get_db
from ..core.utils import log_event, notify
from ..models import Agreement, Offer, ResearchRequest, User
from ..serializers import ser_agreement

router = APIRouter(prefix="/api/v1", tags=["توافق‌نامه همکاری"])


class AgreementIn(BaseModel):
    title: str = ""
    responsibilities: str = ""
    timeline: str = ""
    deliverables: str = ""
    confidentiality: str = ""
    ip_ownership: str = ""


def _get_checked(db: Session, agreement_id: int, user: User) -> tuple[Agreement, ResearchRequest]:
    a = db.get(Agreement, agreement_id)
    if not a:
        raise HTTPException(status_code=404, detail="توافق‌نامه یافت نشد")
    req = db.get(ResearchRequest, a.request_id)
    roles = set(user.roles or [])
    allowed = req.student_id == user.id or roles & {"research_manager", "system_admin"}
    if not allowed:
        offer = db.get(Offer, a.offer_id)
        allowed = offer and offer.professor_id == user.id
    if not allowed:
        raise HTTPException(status_code=403, detail="دسترسی مجاز نیست")
    return a, req


@router.get("/agreements/{agreement_id}", summary="مشاهده توافق‌نامه")
def get_agreement(agreement_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a, req = _get_checked(db, agreement_id, user)
    d = ser_agreement(a)
    d["can_sign_student"] = req.student_id == user.id and not a.student_signed_at
    d["can_sign_professor"] = db.get(Offer, a.offer_id).professor_id == user.id and not a.professor_signed_at
    d["can_edit"] = not (a.student_signed_at and a.professor_signed_at)
    return d


@router.put("/agreements/{agreement_id}", summary="ویرایش بندهای توافق‌نامه (پیش از امضای کامل)")
def edit_agreement(agreement_id: int, body: AgreementIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    a, req = _get_checked(db, agreement_id, user)
    if a.student_signed_at and a.professor_signed_at:
        raise HTTPException(status_code=400, detail="پس از امضای دوطرفه، ویرایش ممکن نیست")
    for key, value in body.model_dump().items():
        if value:
            setattr(a, key, value)
    db.commit()
    return ser_agreement(a)


@router.post("/agreements/{agreement_id}/sign", summary="امضای توافق‌نامه (دانشجو یا استاد)")
def sign_agreement(agreement_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a, req = _get_checked(db, agreement_id, user)
    if a.student_signed_at and a.professor_signed_at:
        raise HTTPException(status_code=400, detail="توافق‌نامه قبلاً توسط دو طرف امضا شده است")

    offer = db.get(Offer, a.offer_id)
    is_student = req.student_id == user.id
    is_prof = offer and offer.professor_id == user.id
    if not (is_student or is_prof):
        raise HTTPException(status_code=403, detail="فقط طرفین توافق می‌توانند امضا کنند")

    from ..core.utils import now_utc
    if is_student and not a.student_signed_at:
        a.student_signed_at = now_utc()
    if is_prof and not a.professor_signed_at:
        a.professor_signed_at = now_utc()

    other_id = offer.professor_id if is_student else req.student_id
    both_signed = bool(a.student_signed_at and a.professor_signed_at)
    log_event(db, "agreement_signed", user.id,
              {"agreement_id": a.id, "request_id": req.id, "fully_signed": both_signed})
    notify(db, other_id, "agreement", "امضای توافق‌نامه همکاری",
           "توافق‌نامه همکاری امضا شد." + (" و پرونده آماده تشکیل پروژه است." if both_signed else " نوبت امضای شماست."),
           f"/chat/{req.id}")

    if both_signed:
        if req.university_approval_required:
            from .. import state_machine as sm
            sm.do_transition(req, "university_review")
            managers = db.query(User).filter(User.roles.contains("research_manager")).all()
            for m in managers:
                notify(db, m.id, "approval", "نیازمند تأیید دانشگاهی",
                       f"درخواست «{req.title}» پس از توافق دوطرفه در انتظار تأیید شماست.", "/requests")
            db.commit()
            return {**ser_agreement(a), "next": "pending_university_approval",
                    "message": "توافق‌نامه امضا شد. پرونده برای تأیید دانشگاه ارسال گردید."}
        from ..project_formation import ProjectFormationError, form_project_from_offer
        try:
            project = form_project_from_offer(db, req, offer, user.id)
            return {**ser_agreement(a), "next": "project_formed", "project_id": project.id,
                    "message": "توافق‌نامه امضا شد و پروژه مشترک تشکیل شد."}
        except ProjectFormationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc))

    db.commit()
    return {**ser_agreement(a), "next": "waiting_other_party"}
