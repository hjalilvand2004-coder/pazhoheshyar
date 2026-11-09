"""سرویس فایل امن — دانلود فقط با کنترل دسترسی، لینک غیرقابل حدس"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..core.config import UPLOAD_DIR
from ..core.deps import get_current_user
from ..core.database import get_db
from ..models import Attachment, Conversation, Message, Project, ProjectMember, ResearchRequest, User
import uuid

router = APIRouter(prefix="/api/v1/files", tags=["فایل‌ها"])


@router.post("/upload", summary="بارگذاری فایل (پیوست گفت‌وگو یا عمومی)")
def upload(file: UploadFile, conversation_id: int | None = None,
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if conversation_id:
        conv = db.get(Conversation, conversation_id)
        if not conv or user.id not in (conv.student_id, conv.professor_id):
            raise HTTPException(status_code=403, detail="دسترسی به این گفت‌وگو مجاز نیست")
    content = file.file.read()
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="حجم فایل بیش از ۱۵ مگابایت است")
    stored = uuid.uuid4().hex
    (UPLOAD_DIR / stored).write_bytes(content)
    att = Attachment(owner_id=user.id, orig_name=file.filename or "file", stored_name=stored,
                     size=len(content), content_type=file.content_type or "")
    db.add(att)
    db.commit()
    return {"id": att.id, "orig_name": att.orig_name, "size": att.size}


@router.get("/{file_id}", summary="دانلود فایل با کنترل دسترسی")
def download(file_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    att = db.get(Attachment, file_id)
    if not att:
        raise HTTPException(status_code=404, detail="فایل یافت نشد")
    if not _can_access(db, att, user):
        raise HTTPException(status_code=403, detail="دسترسی به این فایل مجاز نیست")
    path = UPLOAD_DIR / att.stored_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="محتوای فایل یافت نشد")
    return FileResponse(path, filename=att.orig_name, media_type=att.content_type or "application/octet-stream")


def _can_access(db: Session, att: Attachment, user: User) -> bool:
    roles = set(user.roles or [])
    if att.owner_id == user.id or roles & {"research_manager", "system_admin"}:
        return True
    if att.request_id:
        req = db.get(ResearchRequest, att.request_id)
        if req and req.student_id == user.id:
            return True
        if req and "professor" in roles:
            from ..models import Offer
            return db.query(Offer).filter(Offer.request_id == req.id, Offer.professor_id == user.id).one_or_none() is not None
    if att.project_id:
        return db.query(ProjectMember).filter(ProjectMember.project_id == att.project_id,
                                              ProjectMember.user_id == user.id).one_or_none() is not None
    # پیوست گفت‌وگو: طرفین گفت‌وگویی که پیام حاوی این فایل است
    msg = db.query(Message).filter(Message.attachment_id == att.id).one_or_none()
    if msg:
        conv = db.get(Conversation, msg.conversation_id)
        if conv and user.id in (conv.student_id, conv.professor_id):
            return True
    return False
