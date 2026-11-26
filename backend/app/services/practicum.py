"""درس‌های مقطع‌محور — کارآموزی و درس‌پروژه (کاردانی/کارشناسی) و تحقیق و ارائه (کارشناسی ارشد).

چرخهٔ هر درس: دانشجو گزارش پیشرفت را بارگذاری می‌کند ← استاد مربوطه ارزیابی و بازخورد می‌دهد ←
دانشجو اصلاحات را در نوبت بعدی ارسال می‌کند ← پس از چند رفت‌وبرگشت (رایج ۴ تا ۵ نوبت) درس
تأیید نهایی می‌شود و نمره ثبت می‌گردد. نمایش درس‌ها و اعتبارسنجی‌ها نسبت به مقطع تحصیلی انجام می‌شود.
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, require_roles
from ..core.database import get_db
from ..core.utils import degree_key_of, log_event, notify, now_utc
from ..models import PracticumRecord, PracticumSubmission, PracticumWorkReport, ResearchProfile, User

router = APIRouter(prefix="/api/v1/practicum", tags=["کارآموزی و درس‌پروژه"])

MAX_FILES_PER_SUBMISSION = 5
MAX_FILE_BYTES = 15 * 1024 * 1024        # هم‌سو با سرویس فایل امن

# درس‌ها و مقاطع مجاز — نمایش و اعتبارسنجی هر دو از همین جدول انجام می‌شود
COURSE_TYPES = {
    "internship": {"fa": "کارآموزی", "degrees": ["associate", "bachelor"]},
    "course_project": {"fa": "درس‌پروژه", "degrees": ["associate", "bachelor"]},
    "research_presentation": {"fa": "تحقیق و ارائه", "degrees": ["master"]},
}
DEGREE_LABELS = {
    "associate": "کاردانی",
    "bachelor": "کارشناسی",
    "master": "کارشناسی ارشد",
    "phd": "دکتری",
}
RECORD_STATUS_FA = {
    "active": "فعال",
    "awaiting_review": "در انتظار ارزیابی استاد",
    "needs_revision": "نیازمند اصلاح",
    "approved": "تأییدشده",
    "cancelled": "لغوشده",
}
REPORT_INTERVAL_FA = {"daily": "روزانه", "weekly": "هفتگی"}
MIN_WORK_REPORTS = 5   # حداقل گزارش کار کارآموزی در ترم (استاد می‌تواند بیشتر تعیین کند)
SUBMISSION_STATUS_FA = {
    "pending": "در انتظار ارزیابی",
    "approved": "پذیرفته‌شده",
    "needs_revision": "اصلاح لازم",
}
# راهنمای صادقانه برای دانشجو و استاد
ROUND_GUIDANCE = ("معمولاً پس از ۴ تا ۵ نوبت ارسال و اصلاح، درس تأیید نهایی می‌شود؛ "
                  "تعداد نوبت‌ها بسته به کیفیت کار در اختیار استاد مربوطه است.")


def _profile_of(db: Session, user_id: int) -> ResearchProfile:
    p = db.query(ResearchProfile).filter(ResearchProfile.user_id == user_id).one_or_none()
    if not p:
        p = ResearchProfile(user_id=user_id)
        db.add(p)
        db.flush()
    return p


def _get_record_checked(db: Session, rec_id: int, user: User) -> PracticumRecord:
    r = db.get(PracticumRecord, rec_id)
    if not r:
        raise HTTPException(status_code=404, detail="رکورد درس یافت نشد")
    roles = set(user.roles or [])
    if r.student_id != user.id and r.supervisor_id != user.id \
            and not roles & {"research_manager", "system_admin"}:
        raise HTTPException(status_code=403, detail="فقط دانشجو، استاد مربوطه یا مدیر به این رکورد دسترسی دارد")
    return r


def _ser_submission(s: PracticumSubmission) -> dict:
    return {"id": s.id, "record_id": s.record_id, "round_no": s.round_no, "note": s.note,
            "files": s.files or [], "status": s.status, "status_fa": SUBMISSION_STATUS_FA.get(s.status, s.status),
            "feedback": s.feedback, "supervisor_note": s.supervisor_note,
            "score": s.score,
            "reviewed_at": s.reviewed_at.isoformat() if s.reviewed_at else None,
            "created_at": s.created_at.isoformat() if s.created_at else None}


def _ser_work_report(w: PracticumWorkReport) -> dict:
    return {"id": w.id, "record_id": w.record_id, "report_no": w.report_no, "title": w.title,
            "content": w.content, "hours": w.hours, "status": w.status,
            "status_fa": SUBMISSION_STATUS_FA.get(w.status, w.status), "feedback": w.feedback,
            "reviewed_at": w.reviewed_at.isoformat() if w.reviewed_at else None,
            "created_at": w.created_at.isoformat() if w.created_at else None}


def _ser_record(r: PracticumRecord, student_name="", supervisor_name="") -> dict:
    return {"id": r.id, "student_id": r.student_id, "student_name": student_name,
            "supervisor_id": r.supervisor_id, "supervisor_name": supervisor_name,
            "course_type": r.course_type, "course_fa": COURSE_TYPES.get(r.course_type, {}).get("fa", r.course_type),
            "degree_key": r.degree_key, "degree_fa": DEGREE_LABELS.get(r.degree_key, r.degree_key),
            "title": r.title, "description": r.description, "semester": r.semester,
            "status": r.status, "status_fa": RECORD_STATUS_FA.get(r.status, r.status),
            "round_count": r.round_count, "final_score": r.final_score,
            "report_interval": r.report_interval or "weekly",
            "report_interval_fa": REPORT_INTERVAL_FA.get(r.report_interval or "weekly", "هفتگی"),
            "min_reports": r.min_reports if r.min_reports is not None else MIN_WORK_REPORTS,
            "report_count": r.report_count or 0,
            "supervisor_note": r.supervisor_note,
            "approved_at": r.approved_at.isoformat() if r.approved_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None}


class RecordIn(BaseModel):
    course_type: str
    title: str
    description: str = ""
    semester: str = ""
    supervisor_id: int


class ReviewIn(BaseModel):
    decision: str                 # approved | needs_revision
    feedback: str = ""
    supervisor_note: str = ""
    score: float | None = None


class ScheduleIn(BaseModel):
    report_interval: str          # daily | weekly
    min_reports: int = MIN_WORK_REPORTS


class WorkReportIn(BaseModel):
    title: str
    content: str = ""
    hours: float | None = None


# ============================================================
# اندپوینت‌ها
# ============================================================

@router.get("/meta", summary="درس‌های مجاز نسبت به مقطع تحصیلی من + برچسب‌ها")
def meta(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    dk = degree_key_of(_profile_of(db, user.id).degree)
    is_student = "student" in (user.roles or [])
    courses = [{"key": k, "fa": v["fa"],
                "allowed": dk in v["degrees"] if dk else False}
               for k, v in COURSE_TYPES.items()]
    return {"my_degree": _profile_of(db, user.id).degree or "",
            "my_degree_key": dk,
            "degree_fa": DEGREE_LABELS.get(dk, "") if dk else "",
            "is_student": is_student,
            "courses": courses,
            "round_guidance": ROUND_GUIDANCE,
            "internship_guidance": ("در کارآموزی، زمان‌بندی گزارش کار (روزانه یا هفتگی) را استاد مربوطه تعیین می‌کند؛ "
                                    "برای تأیید نهایی کارآموزی، حداقل ۵ گزارش کار در ترم باید ثبت شده باشد."),
            "degrees": DEGREE_LABELS}


@router.post("/", summary="ایجاد رکورد درس (دانشجو) — درس باید با مقطع تحصیلی سازگار باشد")
def create_record(body: RecordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if "student" not in (user.roles or []):
        raise HTTPException(status_code=403, detail="فقط دانشجو رکورد درس می‌سازد")
    if body.course_type not in COURSE_TYPES:
        raise HTTPException(status_code=400, detail="نوع درس نامعتبر است")
    dk = degree_key_of(_profile_of(db, user.id).degree)
    if not dk:
        raise HTTPException(status_code=400,
                            detail="مقطع تحصیلی در پروفایل شما ثبت نشده است؛ از «پروفایل پژوهشی» مقطع را انتخاب کنید")
    if dk not in COURSE_TYPES[body.course_type]["degrees"]:
        raise HTTPException(status_code=400,
                            detail=f"درس «{COURSE_TYPES[body.course_type]['fa']}» برای مقطع "
                                   f"{DEGREE_LABELS.get(dk, dk)} ارائه نمی‌شود — درس‌های مجاز شما: "
                                   + "، ".join(v["fa"] for k, v in COURSE_TYPES.items() if dk in v["degrees"]))
    sup = db.get(User, body.supervisor_id)
    if not sup or not sup.is_active or "professor" not in (sup.roles or []):
        raise HTTPException(status_code=400, detail="استاد مربوطه باید یک استاد فعال سامانه باشد")
    if not (body.title or "").strip():
        raise HTTPException(status_code=400, detail="عنوان درس را بنویسید")
    r = PracticumRecord(student_id=user.id, supervisor_id=sup.id, course_type=body.course_type,
                        degree_key=dk, title=body.title.strip()[:300],
                        description=body.description, semester=body.semester)
    db.add(r)
    notify(db, sup.id, "practicum_assigned", "ارزیابی درس جدید",
           f"{user.display_name} شما را استاد مربوطهٔ «{COURSE_TYPES[body.course_type]['fa']} — {r.title}» قرار داد.",
           link="/internship" if r.course_type == "internship" else "/practicum")
    log_event(db, "practicum_created", user.id, {"record_id": r.id, "course_type": body.course_type, "degree": dk})
    db.commit()
    return _ser_record(r, user.display_name, sup.display_name)


@router.get("/mine", summary="درس‌های من (دانشجو)")
def my_records(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(PracticumRecord, User)
            .join(User, User.id == PracticumRecord.supervisor_id)
            .filter(PracticumRecord.student_id == user.id)
            .order_by(PracticumRecord.created_at.desc()).all())
    return [_ser_record(r, user.display_name, u.display_name) for r, u in rows]


@router.get("/supervised", summary="درس‌های تحت ارزیابی من (استاد)")
def supervised(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(PracticumRecord, User)
            .join(User, User.id == PracticumRecord.student_id)
            .filter(PracticumRecord.supervisor_id == user.id)
            .order_by(PracticumRecord.updated_at.desc()).all())
    return [_ser_record(r, u.display_name, user.display_name) for r, u in rows]


@router.get("/all", summary="همهٔ رکوردهای درس‌ها (مدیر پژوهش)")
def all_records(user: User = Depends(require_roles("research_manager", "system_admin")),
                db: Session = Depends(get_db)):
    rows = (db.query(PracticumRecord, User)
            .join(User, User.id == PracticumRecord.student_id)
            .order_by(PracticumRecord.updated_at.desc()).limit(300).all())
    out = []
    for r, u in rows:
        sup = db.get(User, r.supervisor_id)
        out.append(_ser_record(r, u.display_name, sup.display_name if sup else ""))
    return out


@router.get("/{rec_id}", summary="نمای کامل رکورد: نوبت‌های ارسال، بازخوردها و وضعیت")
def record_detail(rec_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _get_record_checked(db, rec_id, user)
    student = db.get(User, r.student_id)
    sup = db.get(User, r.supervisor_id)
    subs = (db.query(PracticumSubmission)
            .filter(PracticumSubmission.record_id == r.id)
            .order_by(PracticumSubmission.round_no.desc()).all())
    out = _ser_record(r, student.display_name if student else "", sup.display_name if sup else "")
    out["submissions"] = [_ser_submission(s) for s in subs]
    wrs = (db.query(PracticumWorkReport).filter(PracticumWorkReport.record_id == r.id)
           .order_by(PracticumWorkReport.report_no.desc()).all())
    out["work_reports"] = [_ser_work_report(w) for w in wrs]
    out["is_my_record"] = user.id in (r.student_id, r.supervisor_id)
    return out


@router.post("/{rec_id}/submissions", summary="ارسال گزارش پیشرفت (نوبت جدید) با فایل‌ها")
def submit_report(rec_id: int, note: str = Form(""),
                  files: list[UploadFile] = File(default=[]),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _get_record_checked(db, rec_id, user)
    if r.student_id != user.id:
        raise HTTPException(status_code=403, detail="فقط دانشجوی صاحب رکورد گزارش ارسال می‌کند")
    if r.status == "approved":
        raise HTTPException(status_code=400, detail="این درس تأیید نهایی شده است")
    if r.status == "cancelled":
        raise HTTPException(status_code=400, detail="این رکورد لغو شده است")
    if len(files) > MAX_FILES_PER_SUBMISSION:
        raise HTTPException(status_code=400, detail=f"بیشتر از {MAX_FILES_PER_SUBMISSION} فایل در هر نوبت مجاز نیست")
    import uuid
    from ..core.config import UPLOAD_DIR
    from ..models import Attachment
    saved = []
    for f in files or []:
        content = f.file.read()
        if len(content) > MAX_FILE_BYTES:
            raise HTTPException(status_code=400, detail=f"فایل «{f.filename}» بیش از ۱۵ مگابایت است")
        if len(content) == 0:
            continue
        stored = uuid.uuid4().hex
        (UPLOAD_DIR / stored).write_bytes(content)
        att = Attachment(owner_id=user.id, orig_name=f.filename or "report", stored_name=stored,
                         size=len(content), content_type=f.content_type or "")
        db.add(att)
        db.flush()
        saved.append({"id": att.id, "name": att.orig_name, "size": att.size})
    r.round_count += 1
    r.status = "awaiting_review"
    s = PracticumSubmission(record_id=r.id, round_no=r.round_count, note=note, files=saved)
    db.add(s)
    notify(db, r.supervisor_id, "practicum_submission",
           f"نوبت {r.round_count} — گزارش جدید",
           f"{user.display_name} در «{r.title}» گزارش نوبت {r.round_count} را بارگذاری کرد؛ برای ارزیابی آماده است.",
           link="/internship" if r.course_type == "internship" else "/practicum")
    log_event(db, "practicum_submitted", user.id,
              {"record_id": r.id, "round_no": r.round_count, "files": len(saved)})
    db.commit()
    return {"record": _ser_record(r), "submission": _ser_submission(s)}


@router.post("/submissions/{sub_id}/review", summary="ارزیابی استاد: پذیرش نوبت یا درخواست اصلاح با بازخورد")
def review_submission(sub_id: int, body: ReviewIn, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    if body.decision not in ("approved", "needs_revision"):
        raise HTTPException(status_code=400, detail="تصمیم باید approved یا needs_revision باشد")
    s = db.get(PracticumSubmission, sub_id)
    if not s:
        raise HTTPException(status_code=404, detail="نوبت ارسال یافت نشد")
    r = db.get(PracticumRecord, s.record_id)
    if not r:
        raise HTTPException(status_code=404, detail="رکورد درس یافت نشد")
    if r.supervisor_id != user.id and not (set(user.roles or []) & {"research_manager", "system_admin"}):
        raise HTTPException(status_code=403, detail="فقط استاد مربوطه ارزیابی می‌کند")
    if s.status != "pending":
        raise HTTPException(status_code=400, detail="این نوبت قبلاً ارزیابی شده است")
    if body.decision == "approved" and body.score is not None and not (0 <= body.score <= 20):
        raise HTTPException(status_code=400, detail="نمره باید بین ۰ تا ۲۰ باشد")
    if body.decision == "approved" and r.course_type == "internship":
        need = max(MIN_WORK_REPORTS, r.min_reports or MIN_WORK_REPORTS)
        if (r.report_count or 0) < need:
            raise HTTPException(status_code=400,
                                detail=f"برای تأیید نهایی کارآموزی، حداقل {need} گزارش کار لازم است — "
                                       f"تاکنون {r.report_count or 0} گزارش ثبت شده است")
    s.status = body.decision
    s.feedback = body.feedback
    s.supervisor_note = body.supervisor_note
    s.score = body.score if body.decision == "approved" else None
    s.reviewer_id = user.id
    s.reviewed_at = now_utc()
    if body.decision == "approved":
        r.status = "approved"
        r.final_score = body.score
        r.supervisor_note = body.supervisor_note or body.feedback
        r.approved_at = now_utc()
        notify(db, r.student_id, "practicum_approved", "درس تأیید شد ✓",
               f"«{r.title}» پس از {r.round_count} نوبت تأیید نهایی شد"
               + (f" — نمره: {body.score}" if body.score is not None else "") + ".",
               link="/internship" if r.course_type == "internship" else "/practicum")
        log_event(db, "practicum_approved", user.id,
                  {"record_id": r.id, "rounds": r.round_count, "score": body.score})
    else:
        r.status = "needs_revision"
        notify(db, r.student_id, "practicum_revision", f"نوبت {s.round_no}: اصلاح لازم",
               (body.feedback or "استاد بازخورد ثبت کرد؛ نسخهٔ اصلاح‌شده را در نوبت بعدی ارسال کنید."),
               link="/internship" if r.course_type == "internship" else "/practicum")
        log_event(db, "practicum_revision_requested", user.id,
                  {"record_id": r.id, "round_no": s.round_no})
    db.commit()
    return {"submission": _ser_submission(s), "record": _ser_record(r)}


@router.post("/{rec_id}/schedule", summary="تعیین زمان‌بندی گزارش کار کارآموزی توسط استاد (روزانه/هفتگی)")
def set_schedule(rec_id: int, body: ScheduleIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    r = _get_record_checked(db, rec_id, user)
    if r.supervisor_id != user.id and not (set(user.roles or []) & {"research_manager", "system_admin"}):
        raise HTTPException(status_code=403, detail="فقط استاد مربوطه زمان‌بندی را تعیین می‌کند")
    if r.course_type != "internship":
        raise HTTPException(status_code=400, detail="زمان‌بندی گزارش کار مخصوص درس کارآموزی است")
    if body.report_interval not in ("daily", "weekly"):
        raise HTTPException(status_code=400, detail="زمان‌بندی باید daily یا weekly باشد")
    if not (1 <= body.min_reports <= 30):
        raise HTTPException(status_code=400, detail="حداقل گزارش باید عددی بین ۱ تا ۳۰ باشد")
    need = max(MIN_WORK_REPORTS, body.min_reports)
    r.report_interval = body.report_interval
    r.min_reports = need
    notify(db, r.student_id, "practicum_schedule",
           "زمان‌بندی گزارش کار کارآموزی",
           f"استاد مربوطه برای «{r.title}» گزارش کار {REPORT_INTERVAL_FA[body.report_interval]} تعیین کرد؛ "
           f"برای تأیید نهایی، حداقل {need} گزارش کار در ترم لازم است.",
           link="/internship")
    log_event(db, "practicum_schedule_set", user.id,
              {"record_id": r.id, "interval": body.report_interval, "min_reports": need})
    db.commit()
    return _ser_record(r)


@router.post("/{rec_id}/work-reports", summary="ارسال گزارش کار کارآموزی (هفتگی/روزانه طبق زمان‌بندی استاد)")
def submit_work_report(rec_id: int, body: WorkReportIn, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    r = _get_record_checked(db, rec_id, user)
    if r.student_id != user.id:
        raise HTTPException(status_code=403, detail="فقط دانشجوی صاحب رکورد گزارش کار می‌فرستد")
    if r.course_type != "internship":
        raise HTTPException(status_code=400, detail="گزارش کار مخصوص درس کارآموزی است؛ برای درس‌پروژه از «گزارش پیشرفت» استفاده کنید")
    if r.status == "approved":
        raise HTTPException(status_code=400, detail="این درس تأیید نهایی شده است")
    if r.status == "cancelled":
        raise HTTPException(status_code=400, detail="این رکورد لغو شده است")
    if not (body.title or "").strip():
        raise HTTPException(status_code=400, detail="عنوان گزارش کار را بنویسید (مثلاً «گزارش هفتهٔ اول»)")
    if body.hours is not None and not (0 <= body.hours <= 24 * 7):
        raise HTTPException(status_code=400, detail="ساعت کارکرد نامعتبر است")
    r.report_count = (r.report_count or 0) + 1
    w = PracticumWorkReport(record_id=r.id, report_no=r.report_count, title=body.title.strip()[:300],
                            content=body.content, hours=body.hours)
    db.add(w)
    notify(db, r.supervisor_id, "practicum_work_report",
           f"گزارش کار {r.report_count} — کارآموزی",
           f"{user.display_name} در «{r.title}» گزارش کار شمارهٔ {r.report_count} را ثبت کرد "
           f"(زمان‌بندی {REPORT_INTERVAL_FA.get(r.report_interval or 'weekly', 'هفتگی')}).",
           link="/internship")
    log_event(db, "practicum_work_report_submitted", user.id,
              {"record_id": r.id, "report_no": r.report_count})
    db.commit()
    return {"report": _ser_work_report(w), "record": _ser_record(r)}


@router.post("/work-reports/{wr_id}/review", summary="ارزیابی گزارش کار توسط استاد: پذیرش یا اصلاح با بازخورد")
def review_work_report(wr_id: int, body: ReviewIn, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    if body.decision not in ("approved", "needs_revision"):
        raise HTTPException(status_code=400, detail="تصمیم باید approved یا needs_revision باشد")
    w = db.get(PracticumWorkReport, wr_id)
    if not w:
        raise HTTPException(status_code=404, detail="گزارش کار یافت نشد")
    r = db.get(PracticumRecord, w.record_id)
    if not r:
        raise HTTPException(status_code=404, detail="رکورد درس یافت نشد")
    if r.supervisor_id != user.id and not (set(user.roles or []) & {"research_manager", "system_admin"}):
        raise HTTPException(status_code=403, detail="فقط استاد مربوطه گزارش کار را ارزیابی می‌کند")
    if w.status != "pending":
        raise HTTPException(status_code=400, detail="این گزارش قبلاً ارزیابی شده است")
    w.status = body.decision
    w.feedback = body.feedback
    w.reviewer_id = user.id
    w.reviewed_at = now_utc()
    notify(db, r.student_id, "practicum_work_report_reviewed",
           f"گزارش کار {w.report_no}: {'پذیرفته شد ✓' if body.decision == 'approved' else 'اصلاح لازم'}",
           body.feedback or "استاد مربوطه گزارش کار شما را ارزیابی کرد.",
           link="/internship")
    log_event(db, "practicum_work_report_reviewed", user.id,
              {"record_id": r.id, "report_no": w.report_no, "decision": body.decision})
    db.commit()
    return {"report": _ser_work_report(w), "record": _ser_record(r)}


@router.post("/{rec_id}/cancel", summary="لغو رکورد توسط دانشجو (پیش از تأیید نهایی)")
def cancel_record(rec_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _get_record_checked(db, rec_id, user)
    if r.student_id != user.id:
        raise HTTPException(status_code=403, detail="فقط دانشجوی صاحب رکورد می‌تواند لغو کند")
    if r.status == "approved":
        raise HTTPException(status_code=400, detail="درس تأییدشده قابل لغو نیست")
    r.status = "cancelled"
    log_event(db, "practicum_cancelled", user.id, {"record_id": r.id})
    db.commit()
    return {"ok": True}
