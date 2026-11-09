"""سرویس گفت‌وگو — پیام متنی و فایل، درخواست جلسه، گزارش مزاحمت، کنترل دسترسی"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.config import MESSAGE_HOURLY_LIMIT
from ..core.deps import get_current_user
from ..core.database import get_db
from ..core.utils import log_event, notify, rate_limit
from ..models import Attachment, Conversation, Message, ResearchRequest, User
from ..serializers import ser_conversation, ser_message
from .. import state_machine as sm

router = APIRouter(prefix="/api/v1/conversations", tags=["گفت‌وگو"])


class MessageIn(BaseModel):
    body: str = ""
    kind: str = "text"          # text | file | meeting | meeting_result
    attachment_id: int | None = None


class ReportIn(BaseModel):
    reason: str


def _get_conv_checked(db: Session, conv_id: int, user: User) -> Conversation:
    conv = db.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="گفت‌وگو یافت نشد")
    if user.id not in (conv.student_id, conv.professor_id) and \
            not set(user.roles or []) & {"research_manager", "system_admin"}:
        raise HTTPException(status_code=403, detail="دسترسی به این گفت‌وگو مجاز نیست")
    return conv


@router.post("/by-request/{request_id}/with/{professor_id}", summary="گفت‌وگو درباره درخواست (ایجاد در صورت نبود)")
def open_conversation(request_id: int, professor_id: int, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    from ..services.offers import start_dialogue  # noqa
    req = db.get(ResearchRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="درخواست یافت نشد")
    prof = db.get(User, professor_id)
    if not prof or "professor" not in (prof.roles or []):
        raise HTTPException(status_code=404, detail="استاد یافت نشد")
    if user.id == req.student_id:
        student_id, prof_id = req.student_id, professor_id
    elif user.id == professor_id:
        student_id, prof_id = req.student_id, user.id
    else:
        raise HTTPException(status_code=403, detail="فقط طرفین درخواست می‌توانند گفت‌وگو را آغاز کنند")
    conv = db.query(Conversation).filter(Conversation.request_id == req.id,
                                         Conversation.professor_id == prof_id).one_or_none()
    if not conv:
        conv = Conversation(request_id=req.id, student_id=student_id, professor_id=prof_id)
        db.add(conv)
        db.commit()
    return ser_conversation(conv, db.get(User, student_id), db.get(User, prof_id), req.title)


@router.get("/mine", summary="گفت‌وگوهای من")
def my_conversations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Conversation).filter((Conversation.student_id == user.id) | (Conversation.professor_id == user.id))\
        .order_by(Conversation.created_at.desc()).all()
    out = []
    for c in rows:
        req = db.get(ResearchRequest, c.request_id)
        out.append(ser_conversation(c, db.get(User, c.student_id), db.get(User, c.professor_id),
                                    req.title if req else ""))
    return out


@router.get("/{conversation_id}/messages", summary="پیام‌های گفت‌وگو (اختیاری: بعد از شناسه)")
def messages(conversation_id: int, after: int = 0, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    conv = _get_conv_checked(db, conversation_id, user)
    q = db.query(Message).filter(Message.conversation_id == conv.id)
    if after:
        q = q.filter(Message.id > after)
    rows = q.order_by(Message.id).limit(300).all()
    out = []
    for m in rows:
        att = db.get(Attachment, m.attachment_id) if m.attachment_id else None
        out.append(ser_message(m, db.get(User, m.sender_id), att))
    return out


@router.post("/{conversation_id}/messages", summary="ارسال پیام/فایل/درخواست جلسه")
def send_message(conversation_id: int, body: MessageIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    conv = _get_conv_checked(db, conversation_id, user)
    if not rate_limit(f"msg:{user.id}", MESSAGE_HOURLY_LIMIT, 3600):
        raise HTTPException(status_code=429, detail="سقف ارسال پیام در ساعت پر شده است")
    if body.kind not in ("text", "file", "meeting", "meeting_result"):
        raise HTTPException(status_code=400, detail="نوع پیام نامعتبر است")
    if body.kind in ("text", "meeting", "meeting_result") and not body.body.strip():
        raise HTTPException(status_code=400, detail="متن پیام خالی است")
    msg = Message(conversation_id=conv.id, sender_id=user.id, kind=body.kind,
                  body=body.body, attachment_id=body.attachment_id)
    db.add(msg)
    db.flush()
    req = db.get(ResearchRequest, conv.request_id)
    other_id = conv.professor_id if user.id == conv.student_id else conv.student_id
    label = {"text": "پیام جدید", "file": "فایل پیوست", "meeting": "درخواست جلسه", "meeting_result": "نتیجه جلسه"}[body.kind]
    notify(db, other_id, "message", label, (body.body or "")[:120], f"/chat/{req.id if req else ''}")
    if req and req.status in ("offers_received", "published"):
        sm.do_transition(req, "start_negotiating")
    log_event(db, "message_sent", user.id, {"conversation_id": conv.id, "kind": body.kind})
    db.commit()
    return ser_message(msg, user)


@router.post("/{conversation_id}/report", summary="گزارش مزاحمت یا سوءاستفاده")
def report(conversation_id: int, body: ReportIn, user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    conv = _get_conv_checked(db, conversation_id, user)
    (db.query(Message).filter(Message.conversation_id == conv.id)
     .update({"is_flagged": True}, synchronize_session=False))
    log_event(db, "abuse_reported", user.id,
              {"conversation_id": conv.id, "reason": body.reason})
    for mgr in db.query(User).filter(User.roles.contains("research_manager")).all():
        notify(db, mgr.id, "abuse", "گزارش سوءاستفاده در گفت‌وگو",
               f"کاربر «{user.display_name}» گفت‌وگوی #{conv.id} را گزارش کرد. دلیل: {body.reason[:200]}",
               "/admin")
    db.commit()
    return {"ok": True, "message": "گزارش شما ثبت شد و برای مدیر پژوهش ارسال گردید."}
