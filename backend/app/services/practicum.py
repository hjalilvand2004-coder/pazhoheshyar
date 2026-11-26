"""درس‌های مقطع‌محور — کارآموزی و درس‌پروژه (کاردانی/کارشناسی) و تحقیق و ارائه (کارشناسی ارشد).

چرخهٔ کارآموزی (گردش کار جدید):
  دانشجو کارآموزی را ثبت می‌کند ← استاد مربوطه «پذیرش» و زمان‌بندی گزارش پیشرفت را تعیین می‌کند
  (روزانه / هفتگی / دوهفته‌یکبار) ← از لحظهٔ پذیرش، دانشجو طبق همان برنامه گزارش پیشرفت را
  «بدون انتظار تأیید مرحله‌ای» می‌فرستد ← استاد هر گزارش را با طیف لیکرت ۰ تا ۴ امتیاز می‌دهد ←
  پس از گزارش مرحلهٔ آخر، استاد «تأیید نهایی» را می‌زند و نمرهٔ کارآموزی = سرجمع امتیازها
  (سقف ۲۰) ثبت می‌شود. حداقل ۵ گزارش پیشرفت در ترم برای تأیید نهایی لازم است.

چرخهٔ درس‌پروژه و تحقیق و ارائه (بدون تغییر):
  ارسال نوبت گزارش پیشرفت ← ارزیابی و بازخورد استاد ← اصلاح در نوبت بعد ← تأیید نهایی با نمرهٔ ۰ تا ۲۰.
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, require_roles
from ..core.database import get_db
from ..core.utils import degree_key_of, log_event, notify, now_utc
from ..models import PracticumRecord, PracticumSubmission, ResearchProfile, User

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
    "pending_acceptance": "در انتظار پذیرش استاد",
    "active": "فعال",
    "awaiting_review": "در انتظار ارزیابی استاد",
    "needs_revision": "نیازمند اصلاح",
    "approved": "تأییدشده",
    "cancelled": "لغوشده",
}
REPORT_INTERVAL_FA = {"daily": "روزانه", "weekly": "هفتگی", "biweekly": "دوهفته‌یکبار"}
INTERVAL_DAYS = {"daily": 1, "weekly": 7, "biweekly": 14}
MIN_PROGRESS_REPORTS = 5   # حداقل گزارش پیشرفت کارآموزی در ترم (استاد می‌تواند بیشتر تعیین کند)
LIKERT_MAX = 4             # بالاترین امتیاز طیف لیکرت هر گزارش
SCORE_MAX = 20             # نمرهٔ نهایی کارآموزی از ۲۰ — سرجمع امتیاز لیکرت با سقف ۲۰
SUBMISSION_STATUS_FA = {
    "pending": "در انتظار امتیاز استاد",
    "approved": "امتیاز داده شد",
    "needs_revision": "اصلاح لازم",
}
# راهنمای صادقانه برای دانشجو و استاد
ROUND_GUIDANCE = ("معمولاً پس از ۴ تا ۵ نوبت ارسال و اصلاح، درس تأیید نهایی می‌شود؛ "
                  "تعداد نوبت‌ها بسته به کیفیت کار در اختیار استاد مربوطه است.")
INTERNSHIP_GUIDANCE = ("پس از ثبت کارآموزی، استاد مربوطه پذیرش و زمان‌بندی گزارش پیشرفت را تعیین می‌کند "
                       "(روزانه، هفتگی یا دوهفته‌یکبار). از لحظهٔ پذیرش، دانشجو طبق برنامه گزارش می‌فرستد — "
                       "بدون نیاز به انتظار برای تأیید هر مرحله. استاد هر گزارش را با طیف لیکرت ۰ تا ۴ امتیاز می‌دهد و "
                       "سرجمع امتیازها (سقف ۲۰) نمرهٔ کارآموزی از ۲۰ می‌شود. حداقل ۵ گزارش پیشرفت در ترم لازم است.")


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
            "score": s.score, "likert_score": s.likert_score,
            "reviewed_at": s.reviewed_at.isoformat() if s.reviewed_at else None,
            "created_at": s.created_at.isoformat() if s.created_at else None}


def _internship_stats(db: Session, r: PracticumRecord) -> dict:
    """سنجه‌های زندهٔ کارآموزی: امتیاز تجمعی لیکرت، پیشرفت نسبت به زمان‌بندی و آخرین گزارش."""
    from datetime import timezone

    def _utc(dt):
        # SQLite مقدار زمانی را بدون timezone برمی‌گرداند؛ با UTC هم‌تراز می‌کنیم
        return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt

    subs = (db.query(PracticumSubmission)
            .filter(PracticumSubmission.record_id == r.id).all())
    scored = [s.likert_score for s in subs if s.likert_score is not None]
    interval_days = INTERVAL_DAYS.get(r.report_interval or "weekly", 7)
    start = _utc(r.accepted_at)
    end = _utc(r.approved_at) or now_utc()
    expected = 0
    days_since = 0
    if start and r.status in ("active", "approved"):
        days_since = max(0, (end - start).days)
        expected = days_since // interval_days + (1 if days_since % interval_days else 0)
        expected = max(1, expected)
    last = max((s.created_at for s in subs), default=None)
    return {
        "likert_sum": sum(scored),
        "current_score": min(SCORE_MAX, sum(scored)),
        "scored_count": len(scored),
        "unscored_count": len(subs) - len(scored),
        "expected_reports": expected,
        "days_since_accept": days_since,
        "last_report_at": last.isoformat() if last else None,
    }


def _ser_record(r: PracticumRecord, student_name="", supervisor_name="", db: Session | None = None) -> dict:
    out = {"id": r.id, "student_id": r.student_id, "student_name": student_name,
           "supervisor_id": r.supervisor_id, "supervisor_name": supervisor_name,
           "course_type": r.course_type, "course_fa": COURSE_TYPES.get(r.course_type, {}).get("fa", r.course_type),
           "degree_key": r.degree_key, "degree_fa": DEGREE_LABELS.get(r.degree_key, r.degree_key),
           "title": r.title, "description": r.description, "semester": r.semester,
           "status": r.status, "status_fa": RECORD_STATUS_FA.get(r.status, r.status),
           "round_count": r.round_count, "final_score": r.final_score,
           "report_interval": r.report_interval or "weekly",
           "report_interval_fa": REPORT_INTERVAL_FA.get(r.report_interval or "weekly", "هفتگی"),
           "min_reports": r.min_reports if r.min_reports is not None else MIN_PROGRESS_REPORTS,
           "accepted_at": r.accepted_at.isoformat() if r.accepted_at else None,
           "supervisor_note": r.supervisor_note,
           "approved_at": r.approved_at.isoformat() if r.approved_at else None,
           "created_at": r.created_at.isoformat() if r.created_at else None}
    if db is not None and r.course_type == "internship":
        out.update(_internship_stats(db, r))
    return out


class RecordIn(BaseModel):
    course_type: str
    title: str
    description: str = ""
    semester: str = ""
    supervisor_id: int


class ReviewIn(BaseModel):
    decision: str                 # approved | needs_revision — فقط درس‌پروژه/تحقیق و ارائه
    feedback: str = ""
    supervisor_note: str = ""
    score: float | None = None


class AcceptIn(BaseModel):
    report_interval: str          # daily | weekly | biweekly
    min_reports: int = MIN_PROGRESS_REPORTS


class LikertIn(BaseModel):
    score: int                    # طیف لیکرت ۰ تا ۴
    feedback: str = ""


class FinalIn(BaseModel):
    supervisor_note: str = ""


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
            "internship_guidance": INTERNSHIP_GUIDANCE,
            "likert_max": LIKERT_MAX,
            "score_max": SCORE_MAX,
            "degrees": DEGREE_LABELS}


@router.post("/", summary="ایجاد رکورد درس (دانشجو) — کارآموزی پس از ثبت، در انتظار پذیرش استاد است")
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
    is_internship = body.course_type == "internship"
    r = PracticumRecord(student_id=user.id, supervisor_id=sup.id, course_type=body.course_type,
                        degree_key=dk, title=body.title.strip()[:300],
                        description=body.description, semester=body.semester,
                        status="pending_acceptance" if is_internship else "active")
    db.add(r)
    if is_internship:
        notify(db, sup.id, "practicum_assigned", "پذیرش کارآموزی",
               f"{user.display_name} کارآموزی «{r.title}» را با شما ثبت کرد؛ پذیرش و زمان‌بندی "
               f"گزارش پیشرفت (روزانه/هفتگی/دوهفته‌یکبار) را تعیین کنید.",
               link="/internship")
    else:
        notify(db, sup.id, "practicum_assigned", "ارزیابی درس جدید",
               f"{user.display_name} شما را استاد مربوطهٔ «{COURSE_TYPES[body.course_type]['fa']} — {r.title}» قرار داد.",
               link="/practicum")
    log_event(db, "practicum_created", user.id, {"record_id": r.id, "course_type": body.course_type, "degree": dk})
    db.commit()
    return _ser_record(r, user.display_name, sup.display_name, db)


@router.get("/mine", summary="درس‌های من (دانشجو)")
def my_records(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(PracticumRecord, User)
            .join(User, User.id == PracticumRecord.supervisor_id)
            .filter(PracticumRecord.student_id == user.id)
            .order_by(PracticumRecord.created_at.desc()).all())
    return [_ser_record(r, user.display_name, u.display_name, db) for r, u in rows]


@router.get("/supervised", summary="درس‌های تحت ارزیابی من (استاد)")
def supervised(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(PracticumRecord, User)
            .join(User, User.id == PracticumRecord.student_id)
            .filter(PracticumRecord.supervisor_id == user.id)
            .order_by(PracticumRecord.updated_at.desc()).all())
    return [_ser_record(r, u.display_name, user.display_name, db) for r, u in rows]


@router.get("/all", summary="همهٔ رکوردهای درس‌ها (مدیر پژوهش)")
def all_records(user: User = Depends(require_roles("research_manager", "system_admin")),
                db: Session = Depends(get_db)):
    rows = (db.query(PracticumRecord, User)
            .join(User, User.id == PracticumRecord.student_id)
            .order_by(PracticumRecord.updated_at.desc()).limit(300).all())
    out = []
    for r, u in rows:
        sup = db.get(User, r.supervisor_id)
        out.append(_ser_record(r, u.display_name, sup.display_name if sup else "", db))
    return out


# ============================================================
# داشبورد کارآموزی‌ها — برای مدیرآموزش/مدیرگروه (مدیر پژوهش سامانه)
# ============================================================

@router.get("/internship-dashboard", summary="گزارش کارآموزی‌های تمام‌شده و در جریان + سنجه‌های روند (مدیر)")
def internship_dashboard(user: User = Depends(require_roles("research_manager", "system_admin")),
                         db: Session = Depends(get_db)):
    rows = (db.query(PracticumRecord, User)
            .join(User, User.id == PracticumRecord.student_id)
            .filter(PracticumRecord.course_type == "internship")
            .order_by(PracticumRecord.created_at.desc()).all())
    completed, ongoing = [], []
    for r, u in rows:
        sup = db.get(User, r.supervisor_id)
        sup_name = sup.display_name if sup else ""
        base = _ser_record(r, u.display_name, sup_name, db)
        item = {"id": r.id, "student_name": u.display_name, "supervisor_name": sup_name,
                "title": r.title, "semester": r.semester, "status": r.status,
                "status_fa": RECORD_STATUS_FA.get(r.status, r.status),
                "report_interval_fa": REPORT_INTERVAL_FA.get(r.report_interval or "weekly", "هفتگی"),
                "round_count": r.round_count, "min_reports": r.min_reports or MIN_PROGRESS_REPORTS,
                "final_score": r.final_score,
                "accepted_at": base.get("accepted_at"), "approved_at": base.get("approved_at"),
                "current_score": base.get("current_score"), "likert_sum": base.get("likert_sum"),
                "scored_count": base.get("scored_count"), "unscored_count": base.get("unscored_count"),
                "expected_reports": base.get("expected_reports"), "last_report_at": base.get("last_report_at"),
                "days_since_accept": base.get("days_since_accept")}
        if r.status == "approved":
            completed.append(item)
        elif r.status in ("pending_acceptance", "active"):
            item["progress_ratio"] = (r.round_count / item["expected_reports"]) if item["expected_reports"] else 0
            item["behind_schedule"] = item["progress_ratio"] < 1
            ongoing.append(item)

    stats = {"total": len(rows), "completed": len(completed), "ongoing": len(ongoing),
             "pending_acceptance": sum(1 for o in ongoing if o["status"] == "pending_acceptance"),
             "behind_schedule": sum(1 for o in ongoing if o.get("behind_schedule"))}

    # روند ارسال گزارش‌های پیشرفت — ۱۰ هفتهٔ اخیر
    from datetime import timedelta
    subs = (db.query(PracticumSubmission, PracticumRecord)
            .join(PracticumRecord, PracticumRecord.id == PracticumSubmission.record_id)
            .filter(PracticumRecord.course_type == "internship").all())
    today = now_utc().date()
    week_start = today - timedelta(days=today.weekday())
    per_week = {}
    for s, _r in subs:
        if not s.created_at:
            continue
        d = s.created_at.date()
        ws = d - timedelta(days=d.weekday())
        per_week[ws.isoformat()] = per_week.get(ws.isoformat(), 0) + 1
    submissions_per_week = []
    for i in range(9, -1, -1):
        ws = week_start - timedelta(weeks=i)
        submissions_per_week.append({"week": ws.isoformat(), "count": per_week.get(ws.isoformat(), 0)})

    # میانگین امتیاز لیکرت به تفکیک شمارهٔ گزارش — روند کیفیت
    by_round = {}
    for s, _r in subs:
        if s.likert_score is not None:
            by_round.setdefault(s.round_no, []).append(s.likert_score)
    avg_likert_by_round = [{"round_no": k, "avg": round(sum(v) / len(v), 2), "count": len(v)}
                           for k, v in sorted(by_round.items())]

    status_distribution = [
        {"status": "pending_acceptance", "fa": "در انتظار پذیرش", "count": stats["pending_acceptance"]},
        {"status": "active", "fa": "فعال (در جریان)",
         "count": sum(1 for o in ongoing if o["status"] == "active")},
        {"status": "approved", "fa": "تأییدشده", "count": len(completed)},
        {"status": "cancelled", "fa": "لغوشده", "count": sum(1 for r, _u in rows if r.status == "cancelled")},
    ]
    behind = [o for o in ongoing if o["status"] == "active" and o.get("behind_schedule")]
    return {"stats": stats, "completed": completed, "ongoing": ongoing,
            "behind_schedule": behind,
            "series": {"submissions_per_week": submissions_per_week,
                       "avg_likert_by_round": avg_likert_by_round,
                       "status_distribution": status_distribution}}


@router.get("/{rec_id}", summary="نمای کامل رکورد: نوبت‌های ارسال، امتیازها و وضعیت")
def record_detail(rec_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _get_record_checked(db, rec_id, user)
    student = db.get(User, r.student_id)
    sup = db.get(User, r.supervisor_id)
    subs = (db.query(PracticumSubmission)
            .filter(PracticumSubmission.record_id == r.id)
            .order_by(PracticumSubmission.round_no.desc()).all())
    out = _ser_record(r, student.display_name if student else "", sup.display_name if sup else "", db)
    out["submissions"] = [_ser_submission(s) for s in subs]
    out["is_my_record"] = user.id in (r.student_id, r.supervisor_id)
    return out


@router.post("/{rec_id}/submissions", summary="ارسال گزارش پیشرفت با فایل‌ها — در کارآموزی بدون انتظار تأیید مرحله‌ای")
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
    if r.course_type == "internship" and r.status == "pending_acceptance":
        raise HTTPException(status_code=400,
                            detail="کارآموزی هنوز توسط استاد مربوطه پذیرفته نشده است؛ پس از پذیرش و تعیین "
                                   "زمان‌بندی، ارسال گزارش پیشرفت آغاز می‌شود")
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
    # کارآموزی: وضعیت رکورد «فعال» می‌ماند و گزارش طبق زمان‌بندی آزادانه ارسال می‌شود؛
    # درس‌پروژه/تحقیق و ارائه: رکورد به «در انتظار ارزیابی» می‌رود.
    if r.course_type != "internship":
        r.status = "awaiting_review"
    s = PracticumSubmission(record_id=r.id, round_no=r.round_count, note=note, files=saved)
    db.add(s)
    if r.course_type == "internship":
        notify(db, r.supervisor_id, "practicum_submission",
               f"گزارش پیشرفت {r.round_count} — کارآموزی",
               f"{user.display_name} طبق زمان‌بندی {REPORT_INTERVAL_FA.get(r.report_interval or 'weekly', 'هفتگی')} "
               f"گزارش پیشرفت {r.round_count} کارآموزی «{r.title}» را ثبت کرد.",
               link="/internship")
    else:
        notify(db, r.supervisor_id, "practicum_submission",
               f"نوبت {r.round_count} — گزارش جدید",
               f"{user.display_name} در «{r.title}» گزارش نوبت {r.round_count} را بارگذاری کرد؛ برای ارزیابی آماده است.",
               link="/practicum")
    log_event(db, "practicum_submitted", user.id,
              {"record_id": r.id, "round_no": r.round_count, "files": len(saved)})
    db.commit()
    return {"record": _ser_record(r, db=db), "submission": _ser_submission(s)}


@router.post("/submissions/{sub_id}/review", summary="ارزیابی نوبت در درس‌پروژه/تحقیق و ارائه (کارآموزی از این مسیر استفاده نمی‌کند)")
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
    if r.course_type == "internship":
        raise HTTPException(status_code=400,
                            detail="ارزیابی کارآموزی با طیف لیکرت روی هر گزارش و سپس «تأیید نهایی» انجام می‌شود؛ "
                                   "از گزینه‌های امتیاز طیف لیکرت استفاده کنید")
    if r.supervisor_id != user.id and not (set(user.roles or []) & {"research_manager", "system_admin"}):
        raise HTTPException(status_code=403, detail="فقط استاد مربوطه ارزیابی می‌کند")
    if s.status != "pending":
        raise HTTPException(status_code=400, detail="این نوبت قبلاً ارزیابی شده است")
    if body.decision == "approved" and body.score is not None and not (0 <= body.score <= 20):
        raise HTTPException(status_code=400, detail="نمره باید بین ۰ تا ۲۰ باشد")
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
               link="/practicum")
        log_event(db, "practicum_approved", user.id,
                  {"record_id": r.id, "rounds": r.round_count, "score": body.score})
    else:
        r.status = "needs_revision"
        notify(db, r.student_id, "practicum_revision", f"نوبت {s.round_no}: اصلاح لازم",
               (body.feedback or "استاد بازخورد ثبت کرد؛ نسخهٔ اصلاح‌شده را در نوبت بعدی ارسال کنید."),
               link="/practicum")
        log_event(db, "practicum_revision_requested", user.id,
                  {"record_id": r.id, "round_no": s.round_no})
    db.commit()
    return {"submission": _ser_submission(s), "record": _ser_record(r, db=db)}


@router.post("/submissions/{sub_id}/likert", summary="امتیاز طیف لیکرت استاد روی هر گزارش پیشرفت کارآموزی (۰ تا ۴)")
def score_likert(sub_id: int, body: LikertIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    if not isinstance(body.score, int) or not (0 <= body.score <= LIKERT_MAX):
        raise HTTPException(status_code=400, detail="امتیاز طیف لیکرت باید عددی بین ۰ تا ۴ باشد")
    s = db.get(PracticumSubmission, sub_id)
    if not s:
        raise HTTPException(status_code=404, detail="گزارش یافت نشد")
    r = db.get(PracticumRecord, s.record_id)
    if not r:
        raise HTTPException(status_code=404, detail="رکورد درس یافت نشد")
    if r.course_type != "internship":
        raise HTTPException(status_code=400, detail="طیف لیکرت مخصوص گزارش‌های کارآموزی است")
    if r.supervisor_id != user.id and not (set(user.roles or []) & {"research_manager", "system_admin"}):
        raise HTTPException(status_code=403, detail="فقط استاد مربوطه گزارش را امتیاز می‌دهد")
    if s.likert_score is not None:
        raise HTTPException(status_code=400, detail="این گزارش قبلاً امتیاز گرفته است")
    s.likert_score = body.score
    s.status = "approved"
    s.feedback = body.feedback
    s.reviewer_id = user.id
    s.reviewed_at = now_utc()
    stats = _internship_stats(db, r)
    notify(db, r.student_id, "practicum_likert",
           f"گزارش پیشرفت {s.round_no}: امتیاز {body.score} از {LIKERT_MAX}",
           (body.feedback or "استاد مربوطه گزارش شما را امتیاز داد.")
           + f" — امتیاز تجمعی تاکنون: {min(SCORE_MAX, stats['likert_sum'])} از سقف {SCORE_MAX}.",
           link="/internship")
    log_event(db, "practicum_likert_scored", user.id,
              {"record_id": r.id, "round_no": s.round_no, "likert": body.score})
    db.commit()
    return {"submission": _ser_submission(s), "record": _ser_record(r, db=db)}


@router.post("/{rec_id}/accept", summary="پذیرش کارآموزی و تعیین زمان‌بندی گزارش پیشرفت توسط استاد (روزانه/هفتگی/دوهفته‌یکبار)")
def accept_internship(rec_id: int, body: AcceptIn, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    r = _get_record_checked(db, rec_id, user)
    if r.supervisor_id != user.id and not (set(user.roles or []) & {"research_manager", "system_admin"}):
        raise HTTPException(status_code=403, detail="فقط استاد مربوطه کارآموزی را پذیرش می‌کند")
    if r.course_type != "internship":
        raise HTTPException(status_code=400, detail="پذیرش و زمان‌بندی مخصوص درس کارآموزی است")
    if body.report_interval not in INTERVAL_DAYS:
        raise HTTPException(status_code=400, detail="زمان‌بندی باید daily، weekly یا biweekly باشد")
    if not (1 <= body.min_reports <= 30):
        raise HTTPException(status_code=400, detail="حداقل گزارش باید عددی بین ۱ تا ۳۰ باشد")
    if r.status not in ("pending_acceptance", "active"):
        raise HTTPException(status_code=400, detail="پذیرش فقط برای کارآموزیِ در انتظار پذیرش یا فعال ممکن است")
    first_accept = r.status == "pending_acceptance"
    need = max(MIN_PROGRESS_REPORTS, body.min_reports)
    if first_accept:
        r.accepted_at = now_utc()
        r.status = "active"
    r.report_interval = body.report_interval
    r.min_reports = need
    notify(db, r.student_id, "practicum_accepted", "کارآموزی پذیرفته شد ✓",
           f"استاد مربوطه کارآموزی «{r.title}» را پذیرفت؛ زمان‌بندی گزارش پیشرفت: "
           f"{REPORT_INTERVAL_FA[body.report_interval]} (حداقل {need} گزارش در ترم). "
           f"از امروز طبق همین برنامه گزارش بفرستید — بدون نیاز به انتظار برای تأیید هر مرحله.",
           link="/internship")
    log_event(db, "practicum_accepted", user.id,
              {"record_id": r.id, "interval": body.report_interval, "min_reports": need})
    db.commit()
    return _ser_record(r, db=db)


@router.post("/{rec_id}/final-approve", summary="تأیید نهایی کارآموزی توسط استاد — نمره = سرجمع امتیاز لیکرت (سقف ۲۰)")
def final_approve(rec_id: int, body: FinalIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    r = _get_record_checked(db, rec_id, user)
    if r.supervisor_id != user.id and not (set(user.roles or []) & {"research_manager", "system_admin"}):
        raise HTTPException(status_code=403, detail="فقط استاد مربوطه تأیید نهایی را ثبت می‌کند")
    if r.course_type != "internship":
        raise HTTPException(status_code=400, detail="تأیید نهایی کارآموزی از مسیر ارزیابی نوبت‌ها انجام می‌شود")
    if r.status != "active":
        raise HTTPException(status_code=400, detail="کارآموزی در وضعیت قابل تأیید نیست")
    need = max(MIN_PROGRESS_REPORTS, r.min_reports or MIN_PROGRESS_REPORTS)
    if (r.round_count or 0) < need:
        raise HTTPException(status_code=400,
                            detail=f"برای تأیید نهایی، حداقل {need} گزارش پیشرفت لازم است — تاکنون {r.round_count or 0} گزارش ثبت شده")
    stats = _internship_stats(db, r)
    if stats["unscored_count"] > 0:
        raise HTTPException(status_code=400,
                            detail=f"{stats['unscored_count']} گزارش هنوز امتیاز طیف لیکرت نگرفته؛ ابتدا همهٔ گزارش‌ها را امتیاز دهید")
    if stats["scored_count"] < need:
        raise HTTPException(status_code=400, detail=f"تعداد گزارش‌های امتیازداده‌شده کمتر از حداقل {need} است")
    r.status = "approved"
    r.final_score = float(min(SCORE_MAX, stats["likert_sum"]))
    r.supervisor_note = body.supervisor_note
    r.approved_at = now_utc()
    notify(db, r.student_id, "practicum_approved", "کارآموزی تأیید نهایی شد ✓",
           f"«{r.title}» با {stats['scored_count']} گزارش پیشرفت تأیید شد؛ نمرهٔ نهایی کارآموزی: "
           f"{r.final_score} از {SCORE_MAX} (سرجمع امتیاز طیف لیکرت).",
           link="/internship")
    log_event(db, "practicum_final_approved", user.id,
              {"record_id": r.id, "reports": stats["scored_count"], "likert_sum": stats["likert_sum"],
               "final_score": r.final_score})
    db.commit()
    return {"record": _ser_record(r, db=db)}


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
