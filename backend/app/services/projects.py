"""سرویس فضای مدیریت پروژه — اعضا، وظایف، جلسات، فایل‌ها، پیشرفت و خاتمه"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.config import UPLOAD_DIR
from ..core.deps import get_current_user, require_roles
from ..core.database import get_db
from ..core.utils import log_event, notify, now_utc
from ..models import (
    Attachment, Project, ProjectMeeting, ProjectMember, ProjectTask, ProgressReport, User,
)
from ..serializers import ser_meeting, ser_project, ser_report, ser_task
import uuid

router = APIRouter(prefix="/api/v1/projects", tags=["مدیریت پروژه"])


class TaskIn(BaseModel):
    title: str
    description: str = ""
    assignee_id: int | None = None
    due_date: date | None = None


class TaskPatch(BaseModel):
    status: str | None = None
    description: str | None = None
    assignee_id: int | None = None
    due_date: date | None = None


class MemberIn(BaseModel):
    username: str
    role: str = "member"   # advisor | member | student


class MeetingIn(BaseModel):
    title: str
    scheduled_at: str = ""
    minutes: str = ""


class ProgressIn(BaseModel):
    percent: int
    note: str = ""


class FeedbackIn(BaseModel):
    feedback: str


def _project(db, project_id):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="پروژه یافت نشد")
    return p


def _member(db, project_id, user_id):
    return db.query(ProjectMember).filter(ProjectMember.project_id == project_id,
                                          ProjectMember.user_id == user_id).one_or_none()


def require_access(db, project_id, user: User, manager_ok: bool = True) -> ProjectMember | None:
    p = _project(db, project_id)
    if _member(db, project_id, user.id):
        return _member(db, project_id, user.id)
    if manager_ok and set(user.roles or []) & {"research_manager", "system_admin"}:
        return None
    raise HTTPException(status_code=403, detail="فقط اعضای مجاز پروژه به آن دسترسی دارند")


@router.get("/mine", summary="پروژه‌های من")
def my_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(Project, User).join(User, User.id == Project.lead_professor_id)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .filter(ProjectMember.user_id == user.id).distinct().order_by(Project.created_at.desc()).all())
    out = []
    for p, lead in rows:
        members = db.query(ProjectMember).filter(ProjectMember.project_id == p.id).all()
        umap = {m.user_id: u for m in members if (u := db.get(User, m.user_id))}
        out.append(ser_project(p, lead, members, umap))
    return out


@router.get("/all", summary="همه پروژه‌ها (مدیر پژوهش)")
def all_projects(user: User = Depends(require_roles("research_manager", "system_admin")),
                 db: Session = Depends(get_db)):
    return _list_all(db)


def _list_all(db: Session):
    rows = (db.query(Project, User).join(User, User.id == Project.lead_professor_id)
            .order_by(Project.created_at.desc()).limit(300).all())
    out = []
    for p, lead in rows:
        out.append(ser_project(p, lead, {}))
    return out


@router.get("/{project_id}", summary="جزئیات پروژه (فقط اعضای مجاز)")
def get_project(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_access(db, project_id, user)
    p = _project(db, project_id)
    members = db.query(ProjectMember).filter(ProjectMember.project_id == p.id).all()
    umap = {}
    for m in members:
        u = db.get(User, m.user_id)
        if u:
            umap[m.user_id] = u
    tasks = db.query(ProjectTask).filter(ProjectTask.project_id == p.id).order_by(ProjectTask.id).all()
    meetings = db.query(ProjectMeeting).filter(ProjectMeeting.project_id == p.id).order_by(ProjectMeeting.scheduled_at).all()
    reports = (db.query(ProgressReport).filter(ProgressReport.project_id == p.id)
               .order_by(ProgressReport.created_at.desc()).all())
    files = db.query(Attachment).filter(Attachment.project_id == p.id).all()
    return {
        **ser_project(p, umap.get(p.lead_professor_id), members, umap),
        "tasks": [ser_task(t, umap.get(t.assignee_id)) for t in tasks],
        "meetings": [ser_meeting(m) for m in meetings],
        "reports": [ser_report(r, umap.get(r.author_id)) for r in reports],
        "files": [{"id": f.id, "orig_name": f.orig_name, "size": f.size, "created_at": f.created_at.isoformat()} for f in files],
        "percent": reports[0].percent if reports else 0,
    }


@router.post("/{project_id}/members", summary="افزودن عضو/استاد مشاور (مسئول پروژه)")
def add_member(project_id: int, body: MemberIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _project(db, project_id)
    me = _member(db, p.id, user.id)
    if (not me or me.role != "lead") and not set(user.roles or []) & {"research_manager", "system_admin"}:
        raise HTTPException(status_code=403, detail="فقط مسئول پروژه می‌تواند عضو اضافه کند")
    target = db.query(User).filter(User.username == body.username.strip().lower()).one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="کاربر با این نام کاربری یافت نشد")
    if _member(db, p.id, target.id):
        raise HTTPException(status_code=409, detail="این کاربر قبلاً عضو پروژه است")
    db.add(ProjectMember(project_id=p.id, user_id=target.id, role=body.role, added_by=user.id))
    notify(db, target.id, "project", "عضویت در پروژه پژوهشی",
           f"شما به پروژه «{p.title}» اضافه شدید.", f"/projects/{p.id}")
    log_event(db, "project_member_added", user.id, {"project_id": p.id, "member_id": target.id, "role": body.role})
    db.commit()
    return {"ok": True}


@router.post("/{project_id}/tasks", summary="افزودن وظیفه")
def add_task(project_id: int, body: TaskIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_access(db, project_id, user)
    t = ProjectTask(project_id=project_id, title=body.title, description=body.description,
                    assignee_id=body.assignee_id, due_date=body.due_date)
    db.add(t)
    if body.assignee_id:
        notify(db, body.assignee_id, "task", "وظیفه جدید در پروژه", body.title, f"/projects/{project_id}")
    db.commit()
    return ser_task(t, db.get(User, body.assignee_id) if body.assignee_id else None)


@router.patch("/{project_id}/tasks/{task_id}", summary="به‌روزرسانی وظیفه")
def patch_task(project_id: int, task_id: int, body: TaskPatch, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    require_access(db, project_id, user)
    t = db.get(ProjectTask, task_id)
    if not t or t.project_id != project_id:
        raise HTTPException(status_code=404, detail="وظیفه یافت نشد")
    if body.status and body.status not in ("todo", "doing", "done"):
        raise HTTPException(status_code=400, detail="وضعیت نامعتبر است")
    for key in ("status", "description", "assignee_id", "due_date"):
        if getattr(body, key) is not None:
            setattr(t, key, getattr(body, key))
    if body.status == "done" and t.assignee_id:
        notify(db, t.assignee_id, "task", "وظیفه تکمیل شد", t.title)
    db.commit()
    return ser_task(t, db.get(User, t.assignee_id) if t.assignee_id else None)


@router.post("/{project_id}/meetings", summary="ثبت جلسه (تقویم جلسات)")
def add_meeting(project_id: int, body: MeetingIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_access(db, project_id, user)
    from ..core.utils import iso
    m = ProjectMeeting(project_id=project_id, title=body.title, minutes=body.minutes, created_by=user.id)
    if body.scheduled_at:
        try:
            from datetime import datetime
            m.scheduled_at = datetime.fromisoformat(body.scheduled_at)
        except ValueError:
            raise HTTPException(status_code=400, detail="قالب تاریخ نامعتبر است (ISO)")
    db.add(m)
    members = db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()
    for mem in members:
        if mem.user_id != user.id:
            notify(db, mem.user_id, "meeting", "جلسه پروژه ثبت شد", body.title, f"/projects/{project_id}")
    db.commit()
    return ser_meeting(m)


@router.patch("/{project_id}/meetings/{meeting_id}", summary="ثبت صورت‌جلسه")
def patch_meeting(project_id: int, meeting_id: int, body: MeetingIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    require_access(db, project_id, user)
    m = db.get(ProjectMeeting, meeting_id)
    if not m or m.project_id != project_id:
        raise HTTPException(status_code=404, detail="جلسه یافت نشد")
    if body.title:
        m.title = body.title
    if body.minutes:
        m.minutes = body.minutes
    db.commit()
    return ser_meeting(m)


@router.post("/{project_id}/files", summary="بارگذاری فایل در فضای پروژه")
def upload_file(project_id: int, file: UploadFile, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_access(db, project_id, user)
    content = file.file.read()
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="حجم فایل بیش از ۱۵ مگابایت است")
    stored = uuid.uuid4().hex
    (UPLOAD_DIR / stored).write_bytes(content)
    att = Attachment(owner_id=user.id, orig_name=file.filename or "file", stored_name=stored,
                     size=len(content), content_type=file.content_type or "", project_id=project_id)
    db.add(att)
    db.commit()
    return {"id": att.id, "orig_name": att.orig_name, "size": att.size}


@router.post("/{project_id}/progress", summary="ثبت گزارش پیشرفت (دانشجوی پروژه)")
def add_progress(project_id: int, body: ProgressIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_access(db, project_id, user)
    if not 0 <= body.percent <= 100:
        raise HTTPException(status_code=400, detail="درصد پیشرفت باید بین ۰ تا ۱۰۰ باشد")
    r = ProgressReport(project_id=project_id, author_id=user.id, percent=body.percent, note=body.note)
    db.add(r)
    p = _project(db, project_id)
    lead = db.get(User, p.lead_professor_id)
    if lead and lead.id != user.id:
        notify(db, lead.id, "progress", "گزارش پیشرفت جدید", f"پیشرفت {body.percent}٪ — {body.note[:100]}", f"/projects/{project_id}")
    db.commit()
    return ser_report(r, user)


@router.patch("/{project_id}/progress/{report_id}", summary="بازخورد استاد به گزارش پیشرفت")
def give_feedback(project_id: int, report_id: int, body: FeedbackIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    require_access(db, project_id, user)
    r = db.get(ProgressReport, report_id)
    if not r or r.project_id != project_id:
        raise HTTPException(status_code=404, detail="گزارش یافت نشد")
    r.feedback = body.feedback
    notify(db, r.author_id, "progress", "بازخورد استاد ثبت شد", body.feedback[:120], f"/projects/{project_id}")
    db.commit()
    return ser_report(r, user)


@router.post("/{project_id}/close", summary="خاتمه پروژه (مسئول یا مدیر)")
def close_project(project_id: int, reason: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _project(db, project_id)
    me = _member(db, p.id, user.id)
    allowed = (me and me.role == "lead") or set(user.roles or []) & {"research_manager", "system_admin"}
    if not allowed:
        raise HTTPException(status_code=403, detail="دسترسی مجاز نیست")
    p.status = "closed"
    p.closed_at = now_utc()
    p.closed_reason = reason
    log_event(db, "project_closed", user.id, {"project_id": p.id})
    for mem in db.query(ProjectMember).filter(ProjectMember.project_id == p.id).all():
        notify(db, mem.user_id, "project", "پروژه خاتمه یافت", f"پروژه «{p.title}» بسته شد.")
    db.commit()
    return {"ok": True}
