"""سرویس درخواست‌های پژوهش — ثبت، استخر، وضعیت‌ها، محرمانگی، تأیید دانشگاه"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.config import REQUEST_DAILY_LIMIT, UPLOAD_DIR
from ..core.deps import get_current_user, require_roles
from ..core.database import get_db
from ..core.utils import log_event, notify, now_utc, rate_limit
from ..models import Attachment, Offer, Project, ResearchProfile, ResearchRequest, User
from ..serializers import ser_offer, ser_request
from .. import state_machine as sm
import uuid

router = APIRouter(prefix="/api/v1/requests", tags=["درخواست پژوهش"])


class RequestIn(BaseModel):
    title: str
    summary: str = ""
    problem: str = ""
    goals: str = ""
    field: str = ""
    skills: list[str] = []
    timeline: str = ""
    topic_id: int | None = None
    scope: str = "all"              # all | faculty | selected
    faculty_name: str = ""
    selected_professors: list[int] = []
    secret_details: str = ""
    university_approval_required: bool = False


class StatusIn(BaseModel):
    action: str                      # publish | cancel | close_no_agreement | expire
    reason: str = ""


class ShareSecretIn(BaseModel):
    professor_id: int


def _student(db, uid):
    return db.get(User, uid)


def can_view_request(user: User, req: ResearchRequest, db: Session) -> bool:
    roles = set(user.roles or [])
    if req.student_id == user.id or roles & {"research_manager", "system_admin"}:
        return True
    if "professor" not in roles or req.status not in sm.PUBLIC_STATUSES:
        return False
    if req.scope == "all":
        return True
    if req.scope == "selected":
        return user.id in (req.selected_professors or [])
    if req.scope == "faculty":
        p = db.query(ResearchProfile).filter(ResearchProfile.user_id == user.id).one_or_none()
        prof_faculties = " ".join(filter(None, [getattr(p, "faculty_name", "") or "", p.field_of_study or ""])) if p else ""
        return req.faculty_name.lower() in prof_faculties.lower() or prof_faculties.lower() in req.faculty_name.lower()
    return False


@router.get("/mine", summary="درخواست‌های من (دانشجو)")
def mine(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(ResearchRequest).filter(ResearchRequest.student_id == user.id)\
        .order_by(ResearchRequest.updated_at.desc()).all()
    return [ser_request(r, user, include_secret=True) for r in rows]


@router.get("/pool", summary="استخر پژوهشی — درخواست‌های قابل مشاهده برای استاد (با فیلتر)")
def pool(q: str = "", field: str = "", skill: str = "", status: str = "",
         user: User = Depends(require_roles("professor", "research_manager", "system_admin")),
         db: Session = Depends(get_db)):
    query = db.query(ResearchRequest, User).join(User, User.id == ResearchRequest.student_id)\
        .filter(ResearchRequest.status.in_(list(sm.PUBLIC_STATUSES)))
    rows = query.order_by(ResearchRequest.updated_at.desc()).limit(500).all()
    out = []
    for req, stu in rows:
        if user.id != req.student_id and not set(user.roles or []) & {"research_manager", "system_admin"} \
                and not can_view_request(user, req, db):
            continue
        if q and q.lower() not in (req.title + " " + (req.summary or "")).lower():
            continue
        if field and field.lower() not in (req.field or "").lower():
            continue
        if skill and skill.lower() not in " ".join(req.skills or []).lower():
            continue
        if status and req.status != status:
            continue
        out.append(ser_request(req, stu))
    return out


@router.get("/all", summary="همه درخواست‌ها (مدیر پژوهش)")
def all_requests(status: str = "", user: User = Depends(require_roles("research_manager", "system_admin")),
                 db: Session = Depends(get_db)):
    query = db.query(ResearchRequest, User).join(User, User.id == ResearchRequest.student_id)
    if status:
        query = query.filter(ResearchRequest.status == status)
    rows = query.order_by(ResearchRequest.updated_at.desc()).limit(500).all()
    return [ser_request(r, u, include_secret=True) for r, u in rows]


@router.post("", summary="ثبت درخواست پژوهش (دانشجو) — پیش‌نویس یا انتشار مستقیم")
def create(body: RequestIn, publish_now: bool = False,
           user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    if not rate_limit(f"req:{user.id}", REQUEST_DAILY_LIMIT, 86400):
        raise HTTPException(status_code=429, detail="سقف ثبت درخواست در روز پر شده است؛ فردا تلاش کنید")
    if body.scope not in ("all", "faculty", "selected"):
        raise HTTPException(status_code=400, detail="دامنه نمایش نامعتبر است")
    if body.scope == "faculty" and not body.faculty_name.strip():
        raise HTTPException(status_code=400, detail="برای دامنه دانشکده، نام دانشکده الزامی است")
    if body.scope == "selected" and not body.selected_professors:
        raise HTTPException(status_code=400, detail="برای ارسال به اساتید منتخب، حداقل یک استاد انتخاب کنید")
    req = ResearchRequest(student_id=user.id, **body.model_dump())
    db.add(req)
    db.flush()
    if publish_now:
        sm.do_transition(req, "publish")
    log_event(db, "request_created", user.id, {"request_id": req.id, "title": req.title, "published": publish_now})
    if publish_now:
        log_event(db, "request_published", user.id, {"request_id": req.id})
    db.commit()
    return ser_request(req, user, include_secret=True)


@router.get("/{request_id}", summary="جزئیات درخواست — دسترسی و محرمانگی کنترل می‌شود")
def get_request(request_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    req = db.get(ResearchRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="درخواست یافت نشد")
    roles = set(user.roles or [])
    is_owner = req.student_id == user.id
    is_manager = bool(roles & {"research_manager", "system_admin"})
    has_offer = False
    if "professor" in roles:
        from ..models import Offer as _Offer
        has_offer = db.query(_Offer).filter(_Offer.request_id == req.id, _Offer.professor_id == user.id).one_or_none() is not None
    if not is_owner and not is_manager and not has_offer and not can_view_request(user, req, db):
        raise HTTPException(status_code=403, detail="اجازه مشاهده این درخواست را ندارید")
    student = _student(db, req.student_id)
    include_secret = is_owner or is_manager or user.id in (req.secret_shared_with or [])
    d = ser_request(req, student, include_secret=include_secret)
    d["my_offer"] = None
    if "professor" in roles:
        o = db.query(Offer).filter(Offer.request_id == req.id, Offer.professor_id == user.id)\
            .order_by(Offer.id.desc()).one_or_none()
        d["my_offer"] = ser_offer(o) if o else None
    return d


@router.patch("/{request_id}", summary="ویرایش درخواست (صاحب درخواست، پیش از توافق)")
def update_request(request_id: int, body: RequestIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    req = db.get(ResearchRequest, request_id)
    if not req or req.student_id != user.id:
        raise HTTPException(status_code=404, detail="درخواست یافت نشد")
    if req.status not in ("draft", "published", "offers_received"):
        raise HTTPException(status_code=400, detail="در وضعیت فعلی امکان ویرایش نیست")
    for key, value in body.model_dump().items():
        setattr(req, key, value)
    db.commit()
    return ser_request(req, user, include_secret=True)


@router.post("/{request_id}/status", summary="گذار وضعیت (انتشار، لغو، بستن، انقضا)")
def change_status(request_id: int, body: StatusIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    req = db.get(ResearchRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="درخواست یافت نشد")
    if body.action not in ("publish", "cancel", "close_no_agreement", "expire"):
        raise HTTPException(status_code=400, detail="عملیات نامعتبر")
    if not sm.action_allowed_for(body.action, user, req):
        raise HTTPException(status_code=403, detail="این عملیات برای نقش شما مجاز نیست")
    if body.action == "publish" and not (req.title and req.problem):
        raise HTTPException(status_code=400, detail="برای انتشار، عنوان و شرح مسئله الزامی است")
    if not sm.do_transition(req, body.action):
        raise HTTPException(status_code=400, detail="این گذار وضعیت از حالت فعلی مجاز نیست")
    req.closed_reason = body.reason or req.closed_reason
    log_event(db, f"request_{body.action}", user.id, {"request_id": req.id, "status": req.status})
    if body.action == "publish":
        notify(db, req.student_id, "status", "درخواست شما در استخر پژوهشی منتشر شد", req.title, f"/requests/{req.id}")
    db.commit()
    return ser_request(req, _student(db, req.student_id), include_secret=True)


@router.post("/{request_id}/share-secret", summary="اشتراک جزئیات محرمانه با استاد مشخص")
def share_secret(request_id: int, body: ShareSecretIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    req = db.get(ResearchRequest, request_id)
    if not req or req.student_id != user.id:
        raise HTTPException(status_code=404, detail="درخواست یافت نشد")
    prof = db.get(User, body.professor_id)
    if not prof or "professor" not in (prof.roles or []):
        raise HTTPException(status_code=404, detail="استاد یافت نشد")
    shared = set(req.secret_shared_with or [])
    shared.add(prof.id)
    req.secret_shared_with = list(shared)
    db.commit()
    notify(db, prof.id, "request", "دسترسی به جزئیات محرمانه درخواست",
           f"دانشجو جزئیات محرمانه درخواست «{req.title}» را برای شما باز کرد.", f"/requests/{req.id}")
    db.commit()
    return {"ok": True, "secret_shared_with": req.secret_shared_with}


@router.post("/{request_id}/attachments", summary="بارگذاری پیوست برای درخواست")
def upload_attachment(request_id: int, file: UploadFile,
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    req = db.get(ResearchRequest, request_id)
    if not req or (req.student_id != user.id and not set(user.roles or []) & {"research_manager"}):
        raise HTTPException(status_code=404, detail="درخواست یافت نشد")
    content = file.file.read()
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="حجم فایل بیش از ۱۵ مگابایت است")
    stored = uuid.uuid4().hex  # نام تصادفی — جلوگیری از دسترسی با لینک قابل حدس
    (UPLOAD_DIR / stored).write_bytes(content)
    att = Attachment(owner_id=user.id, orig_name=file.filename or "file", stored_name=stored,
                     size=len(content), content_type=file.content_type or "", request_id=req.id)
    db.add(att)
    db.commit()
    return {"id": att.id, "orig_name": att.orig_name, "size": att.size}


@router.get("/{request_id}/offers", summary="پیشنهادهای همکاری ثبت‌شده برای درخواست")
def request_offers(request_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    req = db.get(ResearchRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="درخواست یافت نشد")
    roles = set(user.roles or [])
    if req.student_id != user.id and not roles & {"research_manager", "system_admin"}:
        # استاد فقط اگر خودش پیشنهاد داده باشد یا حق دیدن داشته باشد
        if not can_view_request(user, req, db):
            raise HTTPException(status_code=403, detail="دسترسی مجاز نیست")
    rows = db.query(Offer, User).join(User, User.id == Offer.professor_id)\
        .filter(Offer.request_id == req.id).order_by(Offer.created_at).all()
    return [ser_offer(o, u) for o, u in rows]


@router.post("/{request_id}/approve", summary="تأیید نهایی دانشگاه (مدیر پژوهش) → تشکیل پروژه")
def university_approve(request_id: int, user: User = Depends(require_roles("research_manager")),
                       db: Session = Depends(get_db)):
    from ..project_formation import ProjectFormationError, form_project_from_offer
    req = db.get(ResearchRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="درخواست یافت نشد")
    if req.status != "pending_university_approval":
        raise HTTPException(status_code=400, detail="این درخواست در انتظار تأیید دانشگاه نیست")
    offer = db.get(Offer, req.current_offer_id) if req.current_offer_id else None
    if not offer:
        raise HTTPException(status_code=400, detail="پیشنهاد منتخب یافت نشد")
    try:
        project = form_project_from_offer(db, req, offer, user.id)
    except ProjectFormationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    log_event(db, "university_approved", user.id, {"request_id": req.id, "project_id": project.id})
    notify(db, req.student_id, "status", "تأیید دانشگاه صادر شد", "پروژه پژوهشی شما تشکیل شد.", f"/projects/{project.id}")
    db.commit()
    return {"project_id": project.id, "status": req.status}
