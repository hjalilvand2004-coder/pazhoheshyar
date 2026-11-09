"""ابزارهای مشترک: زمان، اعلان، ثبت رخداد، محدودسازی ضداسپم"""
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

_rate_buckets: dict[tuple, list] = {}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def notify(db: Session, user_id: int, ntype: str, title: str, body: str = "", link: str = "") -> None:
    if user_id:
        from ..models import Notification
        db.add(Notification(user_id=user_id, type=ntype, title=title, body=body, link=link))


def log_event(db: Session, etype: str, actor_id: int | None, payload: dict | None = None) -> None:
    """ثبت رخداد برای اعلان‌ها، تحلیل‌ها و مصرف سایر سامانه‌های اکوسیستم"""
    from ..models import EventLog
    db.add(EventLog(type=etype, actor_id=actor_id, payload=payload or {}))


def rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    """پنجره ثابت در حافظه؛ True یعنی مجاز"""
    now = time.time()
    start = int(now // window_seconds) * window_seconds
    hits = [t for t in _rate_buckets.setdefault(key, []) if t > now - window_seconds]
    if len(hits) >= limit:
        _rate_buckets[key] = hits
        return False
    hits.append(now)
    _rate_buckets[key] = hits
    return True
