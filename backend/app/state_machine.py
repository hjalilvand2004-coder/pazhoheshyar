"""ماشین وضعیت درخواست پژوهش — گذارهای مجاز با کنترل نقش در بک‌اند"""
from .core.utils import now_utc

REQUEST_STATUSES = {
    "draft": "پیش‌نویس",
    "published": "منتشرشده در استخر",
    "offers_received": "دریافت پیشنهاد",
    "negotiating": "در حال مذاکره",
    "initial_agreement": "توافق اولیه",
    "pending_university_approval": "در انتظار تأیید دانشگاه",
    "connected_to_project": "متصل به پروژه",
    "cancelled": "لغوشده",
    "expired": "منقضی‌شده",
    "closed_no_agreement": "بسته‌شده بدون توافق",
}

OFFER_STATUSES = {
    "sent": "ارسال‌شده",
    "viewed": "دیده‌شده",
    "in_dialogue": "در گفت‌وگو",
    "accepted": "پذیرفته‌شده توسط دانشجو",
    "converted_to_project": "تبدیل‌شده به پروژه",
    "rejected_by_student": "ردشده توسط دانشجو",
    "withdrawn": "پس‌گرفته‌شده",
    "superseded": "جایگزین‌شده (پیشنهاد دیگری انتخاب شد)",
}

# action → (from_statuses, to_status)
TRANSITIONS = {
    "publish": (["draft"], "published"),
    "mark_offers_received": (["published"], "offers_received"),          # داخلی
    "start_negotiating": (["offers_received", "published"], "negotiating"),  # دانشجو گفت‌وگو را آغاز می‌کند
    "accept_offer": (["offers_received", "negotiating", "published"], "initial_agreement"),  # داخلی
    "university_review": (["initial_agreement"], "pending_university_approval"),  # داخلی بعد از امضای دوطرفه
    "university_approve": (["pending_university_approval"], "connected_to_project"),  # مدیر پژوهش
    "cancel": (["draft", "published", "offers_received", "negotiating"], "cancelled"),
    "expire": (["published", "offers_received"], "expired"),             # مدیر پژوهش
    "close_no_agreement": (["published", "offers_received", "negotiating", "initial_agreement", "pending_university_approval"], "closed_no_agreement"),
}

PUBLIC_STATUSES = {"published", "offers_received", "negotiating"}


def can(action: str, status: str) -> bool:
    rule = TRANSITIONS.get(action)
    return bool(rule) and status in rule[0]


def do_transition(req, action: str) -> bool:
    """اعمال گذار روی شیء درخواست؛ برمی‌گرداند که آیا وضعیت تغییر کرد"""
    if not can(action, req.status):
        return False
    req.status = TRANSITIONS[action][1]
    req.updated_at = now_utc()
    return True


def action_allowed_for(action: str, user, req) -> bool:
    """کنترل نقش در بک‌اند — مخفی‌کردن دکمه در فرانت کافی نیست"""
    roles = set(user.roles or [])
    is_owner = req.student_id == user.id
    if action in ("publish", "cancel", "close_no_agreement"):
        return is_owner or bool(roles & {"research_manager"})
    if action in ("expire",):
        return bool(roles & {"research_manager"})
    return False
