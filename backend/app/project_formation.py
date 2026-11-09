"""تشکیل اتمی پروژه — تضمین «دقیقاً یک پروژه» از هر درخواست، با مقاومت در برابر اتصال هم‌زمان"""
from sqlalchemy.exc import IntegrityError

from .core.utils import log_event, notify, now_utc
from .models import Agreement, Offer, Project, ProjectMember, ResearchRequest


class ProjectFormationError(Exception):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


def form_project_from_offer(db, req: ResearchRequest, offer: Offer, actor_id: int) -> Project:
    """تشکیل پروژه از درخواست + پیشنهاد پذیرفته‌شده.
    قاعده‌ها:
      1) وضعیت درخواست باید مجاز باشد (توافق اولیه یا در انتظار تأیید دانشگاه).
      2) فقط یک پیشنهاد می‌تواند به پروژه تبدیل شود (به‌روزرسانی شرطی اتمی).
      3) قید یکتایی Project.request_id مانع پروژه تکراری حتی در اتصال هم‌زمان است.
    """
    if req.status not in ("initial_agreement", "pending_university_approval"):
        raise ProjectFormationError("شرایط تشکیل پروژه هنوز فراهم نیست (توافق دوطرفه/تأیید دانشگاه لازم است)", 400)

    # ۲) به‌روزرسانی شرطی اتمی: فقط یک فراخوان موفق می‌شود پیشنهاد را «تبدیل‌شده» کند
    updated = (
        db.query(Offer)
        .filter(Offer.id == offer.id, Offer.status == "accepted")
        .update({"status": "converted_to_project"}, synchronize_session=False)
    )
    if updated == 0:
        raise ProjectFormationError("این پیشنهاد قبلاً به پروژه تبدیل شده است؛ از اتصال تکراری جلوگیری شد", 409)

    existing = db.query(Project).filter(Project.request_id == req.id).one_or_none()
    if existing:
        raise ProjectFormationError("برای این درخواست قبلاً پروژه تشکیل شده است", 409)

    agreement = db.query(Agreement).filter(Agreement.request_id == req.id).one_or_none()
    if not agreement or not (agreement.student_signed_at and agreement.professor_signed_at):
        raise ProjectFormationError("توافق‌نامه امضاشده دوطرفه یافت نشد", 400)

    project = Project(request_id=req.id, title=req.title, lead_professor_id=offer.professor_id)
    db.add(project)
    db.flush()  # گرفتن شناسه پروژه پیش از ثبت اعضا
    db.add(ProjectMember(project_id=project.id, user_id=offer.professor_id, role="lead", added_by=actor_id))
    db.add(ProjectMember(project_id=project.id, user_id=req.student_id, role="student", added_by=actor_id))

    # بستن سایر پیشنهادهای در جریان
    (
        db.query(Offer)
        .filter(Offer.request_id == req.id, Offer.id != offer.id, Offer.status.in_(["sent", "viewed", "in_dialogue"]))
        .update({"status": "superseded"}, synchronize_session=False)
    )

    req.status = "connected_to_project"
    req.updated_at = now_utc()

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ProjectFormationError("برای این درخواست قبلاً پروژه تشکیل شده است (اتصال هم‌زمان متعارض مسدود شد)", 409)

    log_event(db, "project_formed", actor_id, {
        "project_id": project.id, "request_id": req.id, "offer_id": offer.id,
        "student_id": req.student_id, "professor_id": offer.professor_id,
    })
    notify(db, req.student_id, "project", "پروژه مشترک تشکیل شد",
           f"پروژه «{project.title}» با موفقیت تشکیل شد.", f"/projects/{project.id}")
    notify(db, offer.professor_id, "project", "پروژه مشترک تشکیل شد",
           f"شما مسئول پروژه «{project.title}» هستید.", f"/projects/{project.id}")
    db.commit()
    return project
