"""سرویس اعلام آمادگی و تأیید دوطرفه — پذیرش اتصال نهایی با قفل اتمی"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.config import OFFER_DAILY_LIMIT
from ..core.deps import get_current_user, require_roles
from ..core.database import get_db
from ..core.utils import log_event, notify, rate_limit
from ..models import Agreement, Offer, Project, ResearchProfile, ResearchRequest, User
from ..serializers import ser_agreement, ser_offer
from .. import state_machine as sm
from ..services.requests import can_view_request

router = APIRouter(prefix="/api/v1", tags=["اعلام آمادگی و تأیید"])

ALLOWED_OFFER_FOR_ACCEPT = ("sent", "viewed", "in_dialogue")


class OfferIn(BaseModel):
    message: str = ""
    conditions: str = ""


@router.post("/requests/{request_id}/offers", summary="اعلام آمادگی برای همکاری (استاد)")
def create_offer(request_id: int, body: OfferIn,
                 user: User = Depends(require_roles("professor")), db: Session = Depends(get_db)):
    if not rate_limit(f"offer:{user.id}", OFFER_DAILY_LIMIT, 86400):
        raise HTTPException(status_code=429, detail="سقف اعلام آمادگی در روز پر شده است")
    req = db.get(ResearchRequest, request_id)
    if not req or req.status not in sm.PUBLIC_STATUSES:
        raise HTTPException(status_code=404, detail="درخواست در استخر فعال یافت نشد")
    if not can_view_request(user, req, db):
        raise HTTPException(status_code=403, detail="این درخواست برای شما قابل مشاهده نیست")
    dup = db.query(Offer).filter(Offer.request_id == req.id, Offer.professor_id == user.id,
                                 Offer.status.in_(ALLOWED_OFFER_FOR_ACCEPT)).one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail="شما قبلاً برای این درخواست اعلام آمادگی کرده‌اید")
    # ظرفیت واقعی استاد
    profile = db.query(ResearchProfile).filter(ResearchProfile.user_id == user.id).one_or_none()
    active_projects = db.query(Project).filter(Project.lead_professor_id == user.id,
                                               Project.status == "active").count()
    if profile and profile.capacity and active_projects >= profile.capacity:
        raise HTTPException(status_code=409, detail="ظرفیت پذیرش دانشجوی شما تکمیل است")

    offer = Offer(request_id=req.id, professor_id=user.id, message=body.message, conditions=body.conditions)
    db.add(offer)
    db.flush()
    if req.status == "published":
        sm.do_transition(req, "mark_offers_received")
    log_event(db, "offer_submitted", user.id, {"request_id": req.id, "offer_id": offer.id})
    notify(db, req.student_id, "offer", "اعلام آمادگی جدید برای درخواست شما",
           f"استاد «{user.display_name}» برای درخواست «{req.title}» اعلام آمادگی کرد.", f"/requests/{req.id}")
    db.commit()
    return ser_offer(offer, user)


@router.get("/offers/mine", summary="اعلام‌های آمادگی من (استاد)")
def my_offers(user: User = Depends(require_roles("professor")), db: Session = Depends(get_db)):
    rows = db.query(Offer, ResearchRequest).join(ResearchRequest, ResearchRequest.id == Offer.request_id)\
        .filter(Offer.professor_id == user.id).order_by(Offer.created_at.desc()).all()
    out = []
    for o, req in rows:
        d = ser_offer(o, user)
        d["request_title"] = req.title
        d["request_status"] = req.status
        out.append(d)
    return out


@router.post("/offers/{offer_id}/start-dialogue", summary="آغاز گفت‌وگو با استاد (دانشجو)")
def start_dialogue(offer_id: int, user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    from ..models import Conversation
    offer = db.get(Offer, offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="پیشنهاد یافت نشد")
    req = db.get(ResearchRequest, offer.request_id)
    if not req or req.student_id != user.id:
        raise HTTPException(status_code=403, detail="دسترسی مجاز نیست")
    if offer.status not in ("sent", "viewed", "in_dialogue", "accepted"):
        raise HTTPException(status_code=400, detail="گفت‌وگو برای این پیشنهاد ممکن نیست")
    if offer.status in ("sent", "viewed"):
        offer.status = "in_dialogue"
    conv = db.query(Conversation).filter(Conversation.request_id == req.id,
                                         Conversation.professor_id == offer.professor_id).one_or_none()
    if not conv:
        conv = Conversation(request_id=req.id, student_id=user.id, professor_id=offer.professor_id)
        db.add(conv)
    if req.status in ("offers_received", "published"):
        sm.do_transition(req, "start_negotiating")
    log_event(db, "dialogue_started", user.id, {"request_id": req.id, "offer_id": offer.id})
    notify(db, offer.professor_id, "dialogue", "گفت‌وگوی همکاری آغاز شد",
           f"دانشجو گفت‌وگو درباره درخواست «{req.title}» را آغاز کرد.", f"/chat/{req.id}")
    db.commit()
    return {"conversation_id": conv.id, "request_status": req.status}


@router.post("/offers/{offer_id}/accept", summary="پذیرش پیشنهاد استاد (دانشجو) → توافق اولیه")
def accept_offer(offer_id: int, user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    offer = db.get(Offer, offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="پیشنهاد یافت نشد")
    req = db.get(ResearchRequest, offer.request_id)
    if not req or req.student_id != user.id:
        raise HTTPException(status_code=403, detail="دسترسی مجاز نیست")
    if req.status not in ("published", "offers_received", "negotiating"):
        raise HTTPException(status_code=409, detail="این درخواست در فرایند پذیرش فعال نیست (ممکن است پیشنهاد دیگری انتخاب شده باشد)")
    if offer.status not in ALLOWED_OFFER_FOR_ACCEPT:
        raise HTTPException(status_code=409, detail="این پیشنهاد قابل پذیرش نیست")

    updated = (db.query(Offer)
               .filter(Offer.id == offer.id, Offer.status.in_(ALLOWED_OFFER_FOR_ACCEPT))
               .update({"status": "accepted"}, synchronize_session=False))
    if updated == 0:
        raise HTTPException(status_code=409, detail="پذیرش هم‌زمان مسدود شد؛ وضعیت را بازبینی کنید")

    # بستن سایر پیشنهادها — انتخاب نهایی دانشجو
    (db.query(Offer)
     .filter(Offer.request_id == req.id, Offer.id != offer.id, Offer.status.in_(ALLOWED_OFFER_FOR_ACCEPT))
     .update({"status": "superseded"}, synchronize_session=False))

    req.current_offer_id = offer.id
    sm.do_transition(req, "accept_offer")
    agreement = db.query(Agreement).filter(Agreement.request_id == req.id).one_or_none()
    if not agreement:
        prof = db.get(User, offer.professor_id)
        agreement = Agreement(
            request_id=req.id, offer_id=offer.id, title=req.title,
            responsibilities=(
                f"دانشجو: انجام فعالیت‌های پژوهشی مطابق زمان‌بندی و گزارش‌دهی منظم.\n"
                f"استاد ({prof.display_name if prof else ''}): هدایت علمی، بازبینی خروجی‌ها و پاسخ‌گویی منظم."
            ),
            timeline=req.timeline or "مطابق زمان‌بندی توافق‌شده در گفت‌وگو",
            deliverables="گزارش‌های مرحله‌ای و سند نهایی پژوهش مطابق توافق",
            confidentiality="اطلاعات و ایده‌های محرمانه طرفین بدون رضایت کتبی افشا یا بازاستفاده نمی‌شود.",
            ip_ownership="مالکیت فکری مطابق آیین‌نامه دانشگاه؛ جزئیات مالی/انتشار در توافق رسمی نهایی می‌شود.",
        )
        db.add(agreement)
        db.flush()

    log_event(db, "offer_accepted", user.id, {"request_id": req.id, "offer_id": offer.id})
    notify(db, offer.professor_id, "offer", "پیشنهاد شما پذیرفته شد",
           f"دانشجو پیشنهاد شما برای «{req.title}» را پذیرفت؛ لطفاً توافق‌نامه همکاری را امضا کنید.", f"/chat/{req.id}")

    db.commit()
    return {"agreement": ser_agreement(agreement), "request": {"status": req.status},
            "message": "پیشنهاد پذیرش شد. پس از امضای توافق‌نامه توسط دو طرف، پروژه تشکیل می‌شود"
                       + (" (با تأیید دانشگاه)." if req.university_approval_required else ".")}


@router.post("/offers/{offer_id}/reject", summary="رد پیشنهاد (دانشجو)")
def reject_offer(offer_id: int, user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    offer = db.get(Offer, offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="پیشنهاد یافت نشد")
    req = db.get(ResearchRequest, offer.request_id)
    if not req or req.student_id != user.id:
        raise HTTPException(status_code=403, detail="دسترسی مجاز نیست")
    if offer.status not in ALLOWED_OFFER_FOR_ACCEPT:
        raise HTTPException(status_code=400, detail="این پیشنهاد قابل رد نیست")
    offer.status = "rejected_by_student"
    notify(db, offer.professor_id, "offer", "پیشنهاد شما رد شد",
           f"دانشجو پیشنهاد شما برای «{req.title}» را رد کرد.")
    db.commit()
    return ser_offer(offer)


@router.post("/offers/{offer_id}/withdraw", summary="پس‌گرفتن اعلام آمادگی (استاد)")
def withdraw_offer(offer_id: int, user: User = Depends(require_roles("professor")), db: Session = Depends(get_db)):
    offer = db.get(Offer, offer_id)
    if not offer or offer.professor_id != user.id:
        raise HTTPException(status_code=404, detail="پیشنهاد یافت نشد")
    if offer.status not in ALLOWED_OFFER_FOR_ACCEPT:
        raise HTTPException(status_code=400, detail="این پیشنهاد قابل پس‌گرفتن نیست")
    offer.status = "withdrawn"
    db.commit()
    return ser_offer(offer)


@router.get("/agreements/by-request/{request_id}", summary="توافق‌نامه همکاری درخواست")
def agreement_by_request(request_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    req = db.get(ResearchRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="درخواست یافت نشد")
    allowed = req.student_id == user.id or set(user.roles or []) & {"research_manager", "system_admin"}
    if not allowed:
        offer = db.query(Offer).filter(Offer.request_id == req.id, Offer.professor_id == user.id).one_or_none()
        allowed = bool(offer)
    if not allowed:
        raise HTTPException(status_code=403, detail="دسترسی مجاز نیست")
    a = db.query(Agreement).filter(Agreement.request_id == req.id).one_or_none()
    return ser_agreement(a) if a else None
