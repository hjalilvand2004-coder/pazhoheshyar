"""سرویس رخدادها — تغذیه اعلان‌ها، تحلیل‌ها و سامانه‌های دیگر اکوسیستم دانشجو۳۶۰"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.deps import manager_or_service
from ..core.database import get_db
from ..models import EventLog
from ..serializers import ser_event

router = APIRouter(prefix="/api/v1/events", tags=["رخدادها"])


@router.get("", summary="جریان رخدادها (مدیر پژوهش یا سامانه دیگر با X-Service-Token)")
def list_events(limit: int = 100, etype: str = "",
                _perm: None = Depends(manager_or_service), db: Session = Depends(get_db)):
    q = db.query(EventLog)
    if etype:
        q = q.filter(EventLog.type == etype)
    rows = q.order_by(EventLog.id.desc()).limit(min(limit, 500)).all()
    return [ser_event(e) for e in rows]
