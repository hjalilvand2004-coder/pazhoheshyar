"""سرویس دستیار هوشمند پژوهش — ماژولار و قاعده‌محور.
اصول: هوش مصنوعی فقط دستیار است؛ بدون حذف خودکار؛ بدون احتمال ساختگی؛
همه خروجی‌ها برچسب «داده آزمایشی» دارند و علت پیشنهاد به زبان ساده نمایش داده می‌شود.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.deps import get_current_user
from ..core.database import get_db
from ..core.utils import log_event
from ..models import AiSuggestionLog, Offer, Project, ProjectTask, ResearchProfile, ResearchRequest, User
from ..serializers import ser_profile

router = APIRouter(prefix="/api/v1/ai", tags=["دستیار هوشمند پژوهش"])

DEMO = {"demo": True, "disclaimer": "این پیشنهاد آزمایشی و قاعده‌محور است؛ تصمیم نهایی با کاربر و ضوابط دانشگاه است."}


def _log(db, user_id, kind, inp, out):
    db.add(AiSuggestionLog(user_id=user_id, kind=kind, input_json=inp, output_json=out))


def _overlap(a: list, b: list) -> list[str]:
    a_set = {str(x).strip().lower() for x in (a or []) if str(x).strip()}
    b_set = {str(x).strip().lower() for x in (b or []) if str(x).strip()}
    return sorted(a_set & b_set)


@router.get("/match-professors/{request_id}", summary="تطبیق دانشجو و استاد — با علت پیشنهاد به زبان ساده")
def match_professors(request_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    req = db.get(ResearchRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="درخواست یافت نشد")
    rows = (db.query(ResearchProfile, User)
            .join(User, User.id == ResearchProfile.user_id)
            .filter(User.roles.contains("professor"), User.is_active.is_(True)).all())
    req_skills = [s.lower() for s in (req.skills or [])]
    req_text = f"{req.title} {req.summary} {req.problem} {req.field}".lower()
    suggestions = []
    for p, u in rows:
        if u.id == req.student_id:
            continue
        reasons, score = [], 0
        shared_exp = _overlap(req_skills, p.expertise)
        if shared_exp:
            score += 30
            reasons.append(f"تخصص استاد با مهارت‌های لازم درخواست هم‌پوشانی دارد: {', '.join(shared_exp)}")
        shared_skills = _overlap(req_skills, p.skills)
        if shared_skills:
            score += 15
            reasons.append(f"مهارت‌های مشترک: {', '.join(shared_skills)}")
        field_hit = req.field and (req.field.lower() in " ".join(p.expertise).lower() or
                                   req.field.lower() in (p.field_of_study or "").lower())
        if field_hit:
            score += 20
            reasons.append("حوزه علمی درخواست داخل حوزه‌های کاری استاد است")
        keyword_hits = [k for k in (p.interests or []) if str(k).lower() and str(k).lower() in req_text]
        if keyword_hits:
            score += 15
            reasons.append(f"علاقه‌مندی‌های استاد با موضوع مرتبط است: {', '.join(str(k) for k in keyword_hits)}")
        active = db.query(Project).filter(Project.lead_professor_id == u.id, Project.status == "active").count()
        capacity = p.capacity or 0
        if capacity and active < capacity:
            score += 10
            reasons.append(f"ظرفیت پذیرش دارد ({active} از {capacity} پروژه فعال)")
        elif capacity:
            reasons.append(f"ظرفیت پذیرش تکمیل است ({active} از {capacity}) — پیشنهاد فقط اطلاع‌رسانی است")
        if availability_overlap := _overlap([req.timeline], [p.availability]):
            score += 5
        if not reasons:
            continue
        suggestions.append({
            "professor_id": u.id, "professor_name": u.display_name, "score": min(score, 100),
            "reasons": reasons or ["شباهت کلی موضوع"],
            "capacity": capacity, "active_projects": active,
        })
    suggestions.sort(key=lambda x: x["score"], reverse=True)
    out = {**DEMO, "note": "امتیاز فقط برای مرتب‌سازی نمایش است و باعث حذف خودکار هیچ دانشجویی نمی‌شود.",
           "suggestions": suggestions[:10]}
    _log(db, user.id, "match_professors", {"request_id": request_id}, out)
    db.commit()
    return out


@router.post("/topic-suggestions", summary="پیشنهاد اولیه موضوع پایان‌نامه (بر اساس علایق)")
def topic_suggestions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(ResearchProfile).filter(ResearchProfile.user_id == user.id).one_or_none()
    interests = (p.interests if p else []) or []
    templates = [
        "بررسی و ارزیابی {i} در داده‌های واقعی سازمانی با روش کمی",
        "طراحی و پیاده‌سازی یک راهکار مبتنی بر {i} برای مسئله‌ای مشخص در دانشگاه",
        "مرور نظام‌مند پژوهش‌های اخیر درباره {i} و شناسایی شکاف‌های پژوهشی",
        "ترکیب {i} با رویکرد تحلیل داده برای بهبود یک فرایند آموزشی",
    ]
    items = []
    for i in (interests or ["حوزه تخصصی شما"])[:4]:
        for t in templates:
            items.append({"title": t.format(i=i), "based_on": f"علاقه‌مندی «{i}» در پروفایل شما"})
    out = {**DEMO,
           "note": "این موارد فقط نقطه شروع گفت‌وگو با استاد هستند؛ اعتبار علمی موضوع با استاد راهنما نهایی می‌شود.",
           "suggestions": items[:8]}
    _log(db, user.id, "topic_suggestions", {"interests": interests}, out)
    db.commit()
    return out


@router.get("/talent-analysis", summary="تحلیل استعداد پژوهشی دانشجو")
def talent_analysis(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(ResearchProfile).filter(ResearchProfile.user_id == user.id).one_or_none()
    if not p:
        return {**DEMO, "message": "ابتدا پروفایل پژوهشی خود را کامل کنید.", "areas": []}
    areas, reasons = [], []
    if p.skills:
        areas.append({"area": p.skills[0], "why": "مهارت ثبت‌شده شماست و می‌توانید سریع شروع کنید"})
        reasons.append(f"مهارت اصلی: {p.skills[0]}")
    if p.interests:
        areas.append({"area": p.interests[0], "why": "علقه پژوهشی ثبت‌شده شما — پایداری انگیزه بیشتر"})
        reasons.append(f"علاقه‌مندی: {p.interests[0]}")
    if p.publications:
        areas.append({"area": "ادامه مسیر مقالات قبلی", "why": f"شما {len(p.publications)} اثر ثبت‌شده دارید"})
    if not areas:
        areas.append({"area": "کامل‌کردن پروفایل", "why": "داده کافی برای تحلیل استعداد وجود ندارد"})
    out = {**DEMO, "areas": areas, "profile_completeness": _completeness(p)}
    _log(db, user.id, "talent_analysis", {}, out)
    db.commit()
    return out


def _completeness(p: ResearchProfile) -> int:
    checks = [p.field_of_study, p.degree, p.interests, p.skills, p.research_history, p.availability]
    filled = sum(1 for c in checks if c)
    return int(filled / len(checks) * 100)


@router.post("/request-assistant", summary="دستیار تدوین درخواست — بازخورد قاعده‌محور")
def request_assistant(body: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    title = str(body.get("title", ""))
    problem = str(body.get("problem", ""))
    goals = str(body.get("goals", ""))
    skills = body.get("skills", [])
    feedback = []
    if len(title) < 15:
        feedback.append("عنوان کوتاه است؛ محدوده و متغیر اصلی پژوهش را در عنوان بیاورید.")
    if len(problem) < 80:
        feedback.append("شرح مسئله را دقیق‌تر کنید: چه شکافی، برای چه جامعه‌ای، چه پیامدی دارد؟")
    if len(goals) < 40:
        feedback.append("هدف اصلی و خروجی مورد انتظار را صریح بنویسید.")
    if not skills:
        feedback.append("مهارت‌های لازم را فهرست کنید تا اساتید متناسب راحت‌تر شما را پیدا کنند.")
    if len(title) >= 15 and len(problem) >= 80 and len(goals) >= 40 and skills:
        feedback.append("درخواست شما نسبتاً کامل است؛ برای ایده محرمانه فقط خلاصه عمومی منتشر کنید.")
    out = {**DEMO, "feedback": feedback}
    _log(db, user.id, "request_assistant", {"title": title[:50]}, out)
    db.commit()
    return out


@router.get("/progress-monitor/{project_id}", summary="پایش پیشرفت — شناسایی تأخیر و اقدام اصلاحی")
def progress_monitor(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from ..models import ProjectMember
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="پروژه یافت نشد")
    member = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id).one_or_none()
    if not member and not set(user.roles or []) & {"research_manager", "system_admin"}:
        raise HTTPException(status_code=403, detail="دسترسی مجاز نیست")
    from ..core.utils import now_utc
    today = now_utc().date()
    overdue = [t for t in db.query(ProjectTask).filter(ProjectTask.project_id == project_id).all()
               if t.status != "done" and t.due_date and t.due_date < today]
    actions = []
    for t in overdue:
        actions.append({
            "task": t.title, "suggestion":
                "برای این وظیفه زمان‌بندی بازنگری شود یا به وظیفه‌های کوچک‌تر تقسیم گردد و در جلسه بعدی مطرح شود.",
        })
    out = {**DEMO, "overdue_count": len(overdue), "actions": actions,
           "message": "تأخیری ثبت نشده است." if not overdue else f"{len(overdue)} وظیفه از مهلت گذشته است."}
    _log(db, user.id, "progress_monitor", {"project_id": project_id}, out)
    db.commit()
    return out


@router.get("/journals", summary="پیشنهاد مجله (داده آزمایشی — مرحله ۳ به منابع واقعی وصل می‌شود)")
def journals(field: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    demo_journals = [
        {"name": "مجله نمونه علوم کامپیوتر ایران", "field": "هوش مصنوعی", "index": "ISC (نمونه)", "note": "بازه داوری معمول ۳-۶ ماه"},
        {"name": "نشریه نمونه مهندسی برق و کامپیوتر", "field": "کامپیوتر", "index": "Scopus (نمونه)", "note": "نیازمند مقاله آزمایشی کامل"},
        {"name": "Example International Journal of AI", "field": "هوش مصنوعی", "index": "نمونه", "note": "داده آزمایشی"},
    ]
    out = {**DEMO, "note": "این فهرست صرفاً نمایشی است؛ قبل از ارسال، وضعیت واقعی مجله را از سایت وزارت علوم/ناشر بررسی کنید.",
           "journals": [j for j in demo_journals if not field or field.lower() in j["field"].lower()]}
    db.commit()
    return out


@router.get("/grants", summary="پیشنهاد گرنت (داده آزمایشی — مرحله ۳ به فراخوان‌های واقعی وصل می‌شود)")
def grants(field: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    demo_grants = [
        {"name": "فراخوان نمونه حمایت از پایان‌نامه‌های کاربردی", "field": "همه حوزه‌ها", "deadline": "نمونه: پایان فصل", "amount": "نمونه"},
        {"name": "صندوق نمونه فناوری‌های نوین", "field": "هوش مصنوعی", "deadline": "نمونه", "amount": "نمونه"},
    ]
    out = {**DEMO, "note": "داده‌ها نمایشی است؛ فراخوان‌های معتبر در مرحله ۳ از سامانه‌های رسمی دریافت می‌شوند.",
           "grants": [g for g in demo_grants if not field or field.lower() in g["field"].lower()]}
    db.commit()
    return out


@router.post("/predict-acceptance", summary="برآورد پذیرش و اثر استنادی — صادقانه")
def predict_acceptance(body: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # اصل: بدون داده کافی و مدل ارزیابی‌شده، هیچ عددی تولید نمی‌کنیم
    return {
        "available": False,
        "message": "برای برآورد پذیرش مقاله یا اثر استنادی، داده تاریخی کافی و مدل ارزیابی‌شده لازم است که در این نسخه موجود نیست. هیچ احتمال ساختگی یا تضمین پذیرش ارائه نمی‌شود.",
        "demo": True,
    }
