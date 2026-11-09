"""سرویس بانک موضوعات و الگوهای استاندارد استاد"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, require_roles
from ..core.database import get_db
from ..core.utils import log_event
from ..models import Topic, User
from ..serializers import ser_topic

router = APIRouter(prefix="/api/v1/topics", tags=["بانک موضوعات"])


class TopicIn(BaseModel):
    kind: str = "topic"  # topic | template
    title: str
    field: str = ""
    problem_statement: str = ""
    research_questions: str = ""
    expected_output: str = ""
    suggested_method: str = ""
    required_skills: list[str] = []
    required_data_equipment: str = ""
    estimated_duration: str = ""
    team_size: int = 1
    acceptance_terms: str = ""
    funding_status: str = ""
    ethics_requirements: str = ""


@router.get("", summary="بانک موضوعات و الگوها + جست‌وجو")
def list_topics(q: str = "", kind: str = "", field: str = "",
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Topic, User).join(User, User.id == Topic.owner_id).filter(Topic.is_active.is_(True))
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Topic.title.like(like), Topic.problem_statement.like(like)))
    if kind in ("topic", "template"):
        query = query.filter(Topic.kind == kind)
    if field:
        query = query.filter(Topic.field.like(f"%{field}%"))
    rows = query.order_by(Topic.created_at.desc()).limit(200).all()
    return [ser_topic(t, u) for t, u in rows]


@router.post("", summary="انتشار موضوع یا الگوی استاندارد (استاد)")
def create_topic(body: TopicIn, user: User = Depends(require_roles("professor", "research_manager")),
                 db: Session = Depends(get_db)):
    if body.kind not in ("topic", "template"):
        raise HTTPException(status_code=400, detail="نوع باید topic یا template باشد")
    t = Topic(owner_id=user.id, **body.model_dump())
    db.add(t)
    db.commit()
    log_event(db, "topic_created", user.id, {"topic_id": t.id, "kind": t.kind})
    db.commit()
    return ser_topic(t, user)


@router.get("/{topic_id}", summary="جزئیات موضوع/الگو")
def get_topic(topic_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t, u = _get(db, topic_id)
    return ser_topic(t, u)


def _get(db: Session, topic_id: int):
    row = db.query(Topic, User).join(User, User.id == Topic.owner_id).filter(Topic.id == topic_id).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="موضوع یافت نشد")
    return row


@router.put("/{topic_id}", summary="ویرایش موضوع/الگو (صاحب موضوع)")
def update_topic(topic_id: int, body: TopicIn, user: User = Depends(require_roles("professor", "research_manager")),
                 db: Session = Depends(get_db)):
    t, u = _get(db, topic_id)
    if t.owner_id != user.id and not set(user.roles or []) & {"research_manager"}:
        raise HTTPException(status_code=403, detail="فقط صاحب موضوع می‌تواند ویرایش کند")
    for key, value in body.model_dump().items():
        setattr(t, key, value)
    db.commit()
    return ser_topic(t, u)


@router.delete("/{topic_id}", summary="حذف (غیرفعال‌سازی) موضوع")
def delete_topic(topic_id: int, user: User = Depends(require_roles("professor", "research_manager")),
                 db: Session = Depends(get_db)):
    t, _u = _get(db, topic_id)
    if t.owner_id != user.id and not set(user.roles or []) & {"research_manager"}:
        raise HTTPException(status_code=403, detail="دسترسی مجاز نیست")
    t.is_active = False
    db.commit()
    return {"ok": True}
