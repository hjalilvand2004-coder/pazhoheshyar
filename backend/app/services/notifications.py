"""سرویس اعلان‌ها"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.deps import get_current_user
from ..core.database import get_db
from ..models import Notification, User
from ..serializers import ser_notification

router = APIRouter(prefix="/api/v1/notifications", tags=["اعلان‌ها"])


@router.get("", summary="اعلان‌های من")
def list_notifications(unread_only: bool = False, limit: int = 50,
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Notification).filter(Notification.user_id == user.id)
    if unread_only:
        q = q.filter(Notification.is_read.is_(False))
    rows = q.order_by(Notification.created_at.desc()).limit(min(limit, 200)).all()
    return [ser_notification(n) for n in rows]


@router.get("/count", summary="تعداد اعلان خوانده‌نشده")
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read.is_(False)).count()
    return {"unread": c}


@router.post("/{notification_id}/read", summary="علامت‌گذاری خوانده‌شدن")
def mark_read(notification_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.get(Notification, notification_id)
    if n and n.user_id == user.id:
        n.is_read = True
        db.commit()
    return {"ok": True}


@router.post("/read-all", summary="خواندن همه اعلان‌ها")
def read_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read.is_(False))\
        .update({"is_read": True}, synchronize_session=False)
    db.commit()
    return {"ok": True}
