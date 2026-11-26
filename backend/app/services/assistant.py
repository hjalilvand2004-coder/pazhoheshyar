"""هستهٔ دستیار هوشمند «دانشگاه هوشمند من» — ویجت چت پژوهشیار۳۶۰.

قرارداد ویجت (frontend/public/agent-widget.js):
  POST /api/chat           {message, session_id?, origin?, page?} + اختیاری Bearer JWT → {reply, session_id}
  GET  /api/widget/config  پیکربندی عمومی ویجت (عنوان، سلام اولیه، پرسش‌های سریع)

اصل صادقگی (مطابق فلسفهٔ سامانه): پاسخ فقط از دادهٔ واقعی همین سامانه ساخته می‌شود و هیچ
عدد یا وضعیت ساختگی تولید نمی‌شود. اگر LLM تنظیم شده باشد (LLM_API_URL + LLM_API_KEY در
محیط — نقطهٔ پایانی سازگار با OpenAI، مثل سرویس GLM)، پاسخ با مدل زبانی و کانتکست واقعی
دانشجو تولید می‌شود و در صورت خطا به پاسخ قاعده‌محور برمی‌گردیم؛ بدون LLM هم دستیار کامل
کار می‌کند.
"""
import time
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.config import LLM_API_KEY, LLM_API_URL, LLM_MODEL, LLM_TIMEOUT_SECONDS
from ..core.database import get_db
from ..core.security import decode_token
from ..core.utils import now_utc
from ..models import (AiSuggestionLog, Notification, PracticumRecord, Project,
                      ProjectMember, ProjectTask, ResearchProfile, ResearchRequest, User)

router = APIRouter(tags=["دستیار هوشمند (ویجت)"])

REPORT_INTERVAL_FA = {"daily": "روزانه", "weekly": "هفتگی"}
REQ_STATUS_FA = {
    "draft": "پیش‌نویس", "published": "منتشرشده", "offers_received": "دریافت پیشنهاد",
    "negotiating": "در حال مذاکره", "initial_agreement": "توافق اولیه",
    "pending_university_approval": "در انتظار تأیید دانشگاه", "connected_to_project": "متصل به پروژه",
    "cancelled": "لغوشده", "expired": "منقضی‌شده", "closed_no_agreement": "بسته‌شده",
}
REC_STATUS_FA = {
    "active": "فعال", "awaiting_review": "در انتظار ارزیابی استاد", "needs_revision": "نیازمند اصلاح",
    "approved": "تأییدشده", "cancelled": "لغوشده",
}
COURSE_FA = {"internship": "کارآموزی", "course_project": "درس‌پروژه", "research_presentation": "تحقیق و ارائه"}

WIDGET_TITLE = "دستیار هوشمند پژوهشیار۳۶۰"
WIDGET_SUBTITLE = "متصل به هستهٔ «دانشگاه هوشمند من»"
WIDGET_GREETING = ("سلام! دستیار هوشمند «دانشگاه هوشمند من» در پژوهشیار۳۶۰ هستم؛ "
                   "از وضعیت پژوهشی، کارآموزی و گزارش کار، درس‌پروژه، پروژه‌ها و درخواست‌هایتان بپرسید "
                   "تا بر اساس آخرین داده‌های همین سامانه راهنمایی‌تان کنم.")
WIDGET_QUICK = ["وضعیت من را خلاصه کن", "وضعیت کارآموزی من", "گزارش کار بعدی من",
                "پروژه‌های من", "راهنمای سامانه"]

# نشست‌های چت در حافظه — تک‌پردازه‌ای (uvicorn تک‌ورکر)؛ تاریخچهٔ هر نشست محدود و پاک‌سازی می‌شود
SESSIONS: dict[str, dict] = {}
SESSION_TTL_SECONDS = 3 * 3600
MAX_SESSIONS = 300
MAX_HISTORY = 16


def _touch_session(sid: str, user_id: int | None, message: str, reply: str) -> None:
    now = time.time()
    if len(SESSIONS) > MAX_SESSIONS:
        for k in list(SESSIONS)[: MAX_SESSIONS // 3]:
            SESSIONS.pop(k, None)
    s = SESSIONS.setdefault(sid, {"user_id": user_id, "history": [], "ts": now})
    s["ts"] = now
    if user_id:
        s["user_id"] = user_id
    s["history"] = (s["history"] + [{"role": "user", "text": message[:1000]},
                                    {"role": "assistant", "text": reply[:2000]}])[-MAX_HISTORY:]


def _history_of(sid: str) -> list[dict]:
    return (SESSIONS.get(sid) or {}).get("history") or []


# ============================================================
# کانتکست واقعی دانشجو — فقط داده‌های درست از پایگاه‌داده
# ============================================================

def _profile_completeness(p: ResearchProfile | None) -> int:
    if not p:
        return 0
    checks = [p.field_of_study, p.degree, p.interests, p.skills, p.research_history, p.availability]
    return int(sum(1 for c in checks if c) / len(checks) * 100)


def _student_context(db: Session, user: User) -> dict:
    """آخرین وضعیت دانشجو از پایگاه‌داده — ورودی صادقانهٔ پاسخ‌ساز."""
    p = db.query(ResearchProfile).filter(ResearchProfile.user_id == user.id).one_or_none()
    ctx: dict = {
        "name": user.display_name,
        "roles": [r for r in (user.roles or []) if r],
        "degree": (p.degree if p else "") or "",
        "field_of_study": (p.field_of_study if p else "") or "",
        "profile_completeness_percent": _profile_completeness(p),
        "skills": (p.skills if p else []) or [],
    }

    recs = (db.query(PracticumRecord)
            .filter(PracticumRecord.student_id == user.id)
            .order_by(PracticumRecord.created_at.desc()).all())
    practicum = []
    for r in recs:
        interval_days = 1 if (r.report_interval or "weekly") == "daily" else 7
        practicum.append({
            "course": COURSE_FA.get(r.course_type, r.course_type),
            "title": r.title,
            "status": REC_STATUS_FA.get(r.status, r.status),
            "progress_rounds": r.round_count,
            "work_report_interval": REPORT_INTERVAL_FA.get(r.report_interval or "weekly", "هفتگی"),
            "work_reports_sent": r.report_count,
            "min_required_work_reports": r.min_reports,
            "final_score": r.final_score,
            "supervisor_id": r.supervisor_id,
        })
    ctx["practicum_records"] = practicum

    memberships = db.query(ProjectMember).filter(ProjectMember.user_id == user.id).all()
    proj_ids = [m.project_id for m in memberships]
    projects = []
    for pr in (db.query(Project).filter(Project.id.in_(proj_ids)).all() if proj_ids else []):
        overdue = [t.title for t in db.query(ProjectTask)
                   .filter(ProjectTask.project_id == pr.id).all()
                   if t.status != "done" and t.due_date and t.due_date < now_utc().date()]
        projects.append({"title": pr.title, "status": pr.status,
                         "my_role": next((m.role for m in memberships if m.project_id == pr.id), ""),
                         "overdue_tasks": overdue[:5], "overdue_count": len(overdue)})
    ctx["projects"] = projects

    reqs = (db.query(ResearchRequest).filter(ResearchRequest.student_id == user.id)
            .order_by(ResearchRequest.created_at.desc()).limit(5).all())
    ctx["research_requests"] = [{"title": q.title, "status": REQ_STATUS_FA.get(q.status, q.status)} for q in reqs]

    notifs = (db.query(Notification).filter(Notification.user_id == user.id)
              .order_by(Notification.created_at.desc()).limit(30).all())
    ctx["unread_notifications"] = sum(1 for n in notifs if not n.is_read)
    ctx["latest_notifications"] = [{"title": n.title, "body": n.body[:120]} for n in notifs[:3]]
    return ctx


def _supervisor_names(db: Session, user: User) -> dict[int, str]:
    ids = {r.supervisor_id for r in db.query(PracticumRecord)
           .filter(PracticumRecord.student_id == user.id).all()}
    return {u.id: u.display_name for u in db.query(User).filter(User.id.in_(ids)).all()} if ids else {}


# ============================================================
# پاسخ‌ساز قاعده‌محور — همیشه در دسترس، صادقانه
# ============================================================

def _fa_num(n) -> str:
    return str(n).translate(str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹٫"))


def _internship_lines(ctx: dict, sup_names: dict[int, str]) -> list[str]:
    lines = []
    for r in ctx["practicum_records"]:
        if r["course"] != "کارآموزی":
            continue
        sent, need = r["work_reports_sent"], r["min_required_work_reports"]
        interval_days = 1 if r["work_report_interval"] == "روزانه" else 7
        nxt = f"حداکثر تا {_fa_num(interval_days)} روز دیگر"
        lines.append(
            f"• «{r['title']}» — وضعیت: {r['status']} · استاد مربوطه: {sup_names.get(r['supervisor_id'], '—')} · "
            f"زمان‌بندی گزارش کار: {r['work_report_interval']} · گزارش‌های ارسال‌شده: {_fa_num(sent)} از حداقل "
            f"{_fa_num(need)} · سررسید پیشنهادی گزارش بعدی: {nxt}"
            + (f" · نمرهٔ نهایی: {_fa_num(r['final_score'])}" if r["final_score"] is not None else ""))
    return lines


def _rule_reply(text: str, ctx: dict | None, db: Session, user: User | None) -> str:
    t = (text or "").strip()
    low = t.lower()
    has = lambda *ks: any(k in low or k in t for k in ks)  # noqa: E731

    if ctx is None:  # کاربر وارد نشده
        return ("برای راهنمایی شخصی، ابتدا وارد پژوهشیار۳۶۰ شوید؛ پس از ورود، وضعیت واقعی شما "
                "(کارآموزی، گزارش کار، پروژه‌ها و درخواست‌ها) را می‌بینم و بر همان اساس راهنمایی می‌دهم.\n"
                "سؤال عمومی دربارهٔ سامانه هم می‌پرسید: ثبت درخواست پژوهش، کارآموزی، آزمایشگاه شبیه‌سازی و…")

    sup_names = _supervisor_names(db, user)
    int_lines = _internship_lines(ctx, sup_names)

    if has("سلام", "درود", "خوبی", "هستی"):
        return (f"سلام {ctx['name']}! 👋 من دستیار هوشمند شما هستم. "
                "از وضعیت کارآموزی و گزارش کار، درس‌پروژه، پروژه‌های پژوهشی یا اعلان‌هایتان بپرسید.")

    if has("گزارش کار", "گزارش هفتگی", "گزارش روزانه", "سررسید", "گزارش بعدی"):
        if int_lines:
            return ("زمان‌بندی گزارش کار کارآموزی را استاد مربوطه تعیین می‌کند (روزانه یا هفتگی) و برای "
                    "تأیید نهایی کارآموزی، حداقل ۵ گزارش در ترم لازم است:\n" + "\n".join(int_lines) +
                    "\nبرای ارسال، منوی «کارآموزی» ← نمایش رکورد ← فرم «گزارش کار».")
        return "رکورد کارآموزی فعالی ندارید؛ از منوی «کارآموزی» با انتخاب استاد مربوطه ثبتش کنید."

    if has("کارآموزی"):
        if int_lines:
            return ("وضعیت کارآموزی شما بر اساس آخرین دادهٔ سامانه:\n" + "\n".join(int_lines) +
                    "\nیادآوری: بدون حداقل ۵ گزارش کار، استاد نمی‌تواند کارآموزی را تأیید نهایی کند.")
        return ("رکورد کارآموزی ثبت نکرده‌اید. از منوی «کارآموزی» فرم ثبت را باز کنید: استاد مربوطه، "
                "عنوان محل کارآموزی و نیم‌سال را وارد کنید. پس از تأیید استاد، زمان‌بندی گزارش کار "
                "(روزانه/هفتگی) همان‌جا مشخص می‌شود.")

    if has("درس‌پروژه", "درس پروژه", "تحقیق و ارائه"):
        rows = [r for r in ctx["practicum_records"] if r["course"] in ("درس‌پروژه", "تحقیق و ارائه")]
        if rows:
            return "درس‌های عملی شما:\n" + "\n".join(
                f"• «{r['title']}» ({r['course']}) — {r['status']} · نوبت‌های گزارش پیشرفت: {_fa_num(r['progress_rounds'])}"
                + (f" · نمره: {_fa_num(r['final_score'])}" if r["final_score"] is not None else "")
                for r in rows)
        return ("درس‌پروژه یا تحقیق و ارائه فعالی ندارید؛ از منوی «درس‌پروژه و تحقیق و ارائه» ثبت کنید "
                "(مطابق مقطع تحصیلی‌تان).")

    if has("پروژه", "پروژه‌ها", "وظیفه", "تاخیر", "تأخیر"):
        if ctx["projects"]:
            return "وضعیت پروژه‌های شما:\n" + "\n".join(
                f"• «{p['title']}» — وضعیت: {p['status']}"
                + (f" · {_fa_num(p['overdue_count'])} وظیفهٔ از مهلت گذشته!" if p["overdue_count"]
                   else " · وظیفهٔ عقب‌افتاده ندارید") for p in ctx["projects"])
        return "پروژهٔ فعالی ندارید؛ از استخر پژوهشی یا درخواست‌هایتان می‌توانید پروژه بسازید."

    if has("درخواست", "استاد پیشنهاد", "پیشنهاد"):
        if ctx["research_requests"]:
            return "آخرین درخواست‌های پژوهشی شما:\n" + "\n".join(
                f"• «{q['title']}» — {q['status']}" for q in ctx["research_requests"])
        return "درخواست پژوهشی ثبت نکرده‌اید؛ از «ثبت درخواست پژوهش» شروع کنید."

    if has("اعلان", "پیام", "خوانده‌نشده"):
        lines = [f"• {n['title']}" for n in ctx["latest_notifications"]]
        return (f"{_fa_num(ctx['unread_notifications'])} اعلان خوانده‌نشده دارید."
                + ("\nآخرین‌ها:\n" + "\n".join(lines) if lines else ""))

    if has("پروفایل", "مهارت", "رزومه"):
        return (f"کاملیت پروفایل پژوهشی شما {_fa_num(ctx['profile_completeness_percent'])}٪ است؛ "
                f"مقطع: {ctx['degree'] or 'ثبت‌نشده'} · حوزه: {ctx['field_of_study'] or 'ثبت‌نشده'} · "
                f"مهارت‌ها: {'، '.join(ctx['skills'][:6]) or 'ثبت‌نشده'}. "
                "پروفایل کامل‌تر = پیشنهاد موضوع و تطبیق استاد دقیق‌تر. از منوی «پروفایل پژوهشی» تکمیلش کنید.")

    if has("ورود", "sso", "اس‌اس‌او", "رمز", "حساب"):
        return ("ورود یکپارچه (SSO) روی پرتال دانشجویار۳۶۰ تنظیم است؛ اگر با حساب پرتال مشکل دارید، "
                "از منوی مدیریت «تنظیمات ورود یکپارچه» را بررسی کنید یا با پشتیبان پرتال تماس بگیرید. "
                "حساب‌های آزمایشی سامانه: student1 / prof1 / manager1 / admin1 با رمز 12345678.")

    if has("وضعیت", "خلاصه", "چطورم", "امروز"):
        parts = []
        if int_lines:
            parts.append("کارآموزی:\n" + "\n".join(int_lines))
        other = [r for r in ctx["practicum_records"] if r["course"] != "کارآموزی"]
        if other:
            parts.append("درس‌های عملی دیگر:\n" + "\n".join(
                f"• «{r['title']}» ({r['course']}) — {r['status']}" for r in other))
        if ctx["projects"]:
            parts.append("پروژه‌ها:\n" + "\n".join(
                f"• «{p['title']}» — {p['status']}"
                + (f" · {_fa_num(p['overdue_count'])} وظیفهٔ عقب‌افتاده" if p["overdue_count"] else "")
                for p in ctx["projects"]))
        if ctx["research_requests"]:
            parts.append("درخواست‌ها:\n" + "\n".join(f"• «{q['title']}» — {q['status']}" for q in ctx["research_requests"]))
        parts.append(f"اعلان خوانده‌نشده: {_fa_num(ctx['unread_notifications'])} · "
                     f"کاملیت پروفایل: {_fa_num(ctx['profile_completeness_percent'])}٪")
        return f"{ctx['name']} عزیز، خلاصهٔ وضعیت شما بر اساس آخرین دادهٔ سامانه:\n" + "\n".join(parts)

    if has("راهنما", "چطور", "آموزش", "کدوم منو", "کجا"):
        return ("راهنمای سریع پژوهشیار۳۶۰:\n"
                "• «ثبت درخواست پژوهش» — شروع همکاری با استاد\n"
                "• «کارآموزی» — ثبت کارآموزی، گزارش کار روزانه/هفتگی و حداقل ۵ گزارش در ترم\n"
                "• «درس‌پروژه و تحقیق و ارائه» — چرخهٔ گزارش پیشرفت تا تأیید نهایی\n"
                "• «پروژه‌های من» و «فضای پژوهش» — نگارش مشترک سند پژوهش\n"
                "• «آزمایشگاه شبیه‌سازی» — تحلیل دیتاست و مدل‌ها\n"
                "هرکدام را بپرسید تا دقیق‌تر راهنمایی کنم.")

    return ("دقیق نمی‌دانم و چیزی ساختگی نمی‌گویم 😊 می‌توانید بپرسید: «وضعیت من را خلاصه کن»، "
            "«وضعیت کارآموزی من»، «گزارش کار بعدی من»، «پروژه‌های من» یا «راهنمای سامانه».")


# ============================================================
# پاسخ‌ساز LLM (اختیاری) — با کانتکست واقعی؛ در خطا به قاعده‌محور برمی‌گردد
# ============================================================

SYSTEM_PROMPT = """تو «دستیار هوشمند دانشگاه هوشمند من» در سامانه پژوهشیار۳۶۰ هستی.
قواعد اکیداً الزامی:
1) فقط بر اساس «کانتکست واقعی دانشجو» که در پیام سیستم داده می‌شود پاسخ بده؛ هیچ عدد، نمره، تاریخ یا وضعیت از خودت نساز.
2) اگر داده‌ای در کانتکست نیست، صادقانه بگو «این مورد در سامانه ثبت نشده» و راهنمایی عمومی بده.
3) فارسی روان، لحن دوستانه و کوتاه (حداکثر ۸ خط)، از بولت استفاده کن، راهکار عملی بده.
4) دربارهٔ کارآموزی یادآوری کن: زمان‌بندی گزارش کار (روزانه/هفتگی) را استاد تعیین می‌کند و حداقل ۵ گزارش کار در ترم برای تأیید نهایی لازم است.
5) تصمیم‌های اداری و نمره با استاد/دانشگاه است؛ تو فقط راهنمایی می‌کنی."""


def _llm_reply(message: str, history: list[dict], ctx: dict | None) -> str | None:
    if not (LLM_API_URL and LLM_API_KEY):
        return None
    import json as _json
    sys = SYSTEM_PROMPT + ("\n\nکانتکست واقعی دانشجو (JSON):\n" + _json.dumps(ctx, ensure_ascii=False)
                           if ctx else "\n\nکاربر وارد سامانه نشده است؛ فقط راهنمایی عمومی بده و از او بخواه وارد شود.")
    msgs = [{"role": "system", "content": sys}]
    msgs += [{"role": h["role"], "content": h["text"]} for h in history]
    msgs.append({"role": "user", "content": message})
    try:
        r = httpx.post(LLM_API_URL, timeout=LLM_TIMEOUT_SECONDS, headers={
            "Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"},
            json={"model": LLM_MODEL, "messages": msgs, "temperature": 0.3, "max_tokens": 700})
        r.raise_for_status()
        data = r.json()
        reply = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()
        return reply or None
    except Exception:
        return None


# ============================================================
# اندپوینت‌ها (قرارداد ویجت)
# ============================================================

class ChatIn(BaseModel):
    message: str
    session_id: str | None = None
    origin: str | None = None
    page: str | None = None


def _user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    payload = decode_token(auth.removeprefix("Bearer ").strip())
    if not payload:
        return None
    user = db.get(User, int(payload.get("sub", 0) or 0))
    return user if user and user.is_active else None


@router.post("/api/chat", summary="نقطهٔ پایانی ویجت دستیار — پاسخ بر اساس آخرین وضعیت کاربر")
def chat(body: ChatIn, user: User | None = Depends(_user_optional),
         db: Session = Depends(get_db)):
    message = (body.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="متن پیام خالی است")
    if len(message) > 2000:
        message = message[:2000]
    sid = body.session_id or uuid.uuid4().hex
    history = _history_of(sid)
    ctx = _student_context(db, user) if user else None
    reply = _llm_reply(message, history, ctx) or _rule_reply(message, ctx, db, user)
    _touch_session(sid, user.id if user else None, message, reply)
    if user:
        db.add(AiSuggestionLog(user_id=user.id, kind="widget_chat",
                               input_json={"message": message[:300], "page": body.page or ""},
                               output_json={"reply": reply[:1500], "sid": sid, "origin": body.origin or ""}))
        db.commit()
    return {"reply": reply, "session_id": sid}


@router.get("/api/widget/config", summary="پیکربندی عمومی ویجت دستیار (بدون احراز هویت)")
def widget_config():
    return {"title": WIDGET_TITLE, "subtitle": WIDGET_SUBTITLE, "greeting": WIDGET_GREETING,
            "quick_questions": WIDGET_QUICK, "position": "bl",
            "accent": "#4f46e5", "accent2": "#0f766e", "require_auth": False, "version": "1.2.0"}
