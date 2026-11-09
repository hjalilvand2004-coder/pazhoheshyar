"""سریالایزر خروجی — با کنترل فیلدهای حساس (سوابق کامل دانشجو به‌صورت عمومی نمایش داده نمی‌شوند)"""
from .core.utils import iso
from .models import (
    Agreement, Attachment, Conversation, EventLog, Message, Notification, Offer,
    Project, ProjectMember, ProjectTask, ProgressReport, ProjectMeeting,
    ResearchProfile, ResearchRequest, Topic, User,
)

ROLE_LABELS = {"student": "دانشجو", "professor": "استاد", "research_manager": "مدیر پژوهش", "system_admin": "مدیر سامانه"}


def ser_user(u: User) -> dict:
    return {
        "id": u.id, "username": u.username, "display_name": u.display_name,
        "roles": u.roles or [], "role_labels": [ROLE_LABELS.get(r, r) for r in (u.roles or [])],
        "sso_linked": bool(u.sso_issuer and u.sso_sub),
        "is_active": u.is_active,
    }


def ser_profile(p: ResearchProfile, full: bool = False) -> dict:
    d = {
        "user_id": p.user_id, "field_of_study": p.field_of_study, "faculty_name": getattr(p, "faculty_name", ""), "degree": p.degree,
        "interests": p.interests or [], "skills": p.skills or [], "bio": p.bio,
        "availability": p.availability, "collaboration_type": p.collaboration_type,
        "research_goal": p.research_goal,
        "expertise": p.expertise or [], "methods_tools": p.methods_tools,
        "capacity": p.capacity, "conditions": p.conditions,
        "academic_data": p.academic_data or {}, "updated_at": iso(p.updated_at),
    }
    if full:  # فقط صاحب پروفایل و مدیران
        d.update({"research_history": p.research_history, "publications": p.publications or []})
    return d


def ser_topic(t: Topic, owner: User | None = None) -> dict:
    return {
        "id": t.id, "kind": t.kind, "title": t.title, "field": t.field,
        "problem_statement": t.problem_statement, "research_questions": t.research_questions,
        "expected_output": t.expected_output, "suggested_method": t.suggested_method,
        "required_skills": t.required_skills or [], "required_data_equipment": t.required_data_equipment,
        "estimated_duration": t.estimated_duration, "team_size": t.team_size,
        "acceptance_terms": t.acceptance_terms, "funding_status": t.funding_status,
        "ethics_requirements": t.ethics_requirements, "is_active": t.is_active,
        "owner_id": t.owner_id, "owner_name": owner.display_name if owner else None,
        "created_at": iso(t.created_at),
    }


def ser_request(r: ResearchRequest, student: User | None = None, include_secret: bool = False) -> dict:
    d = {
        "id": r.id, "student_id": r.student_id,
        "student_name": student.display_name if student else None,
        "title": r.title, "summary": r.summary, "problem": r.problem, "goals": r.goals,
        "field": r.field, "skills": r.skills or [], "timeline": r.timeline,
        "topic_id": r.topic_id, "scope": r.scope, "faculty_name": r.faculty_name,
        "status": r.status, "university_approval_required": r.university_approval_required,
        "current_offer_id": r.current_offer_id, "closed_reason": r.closed_reason,
        "created_at": iso(r.created_at), "updated_at": iso(r.updated_at),
    }
    if include_secret:
        d["secret_details"] = r.secret_details
    return d


def ser_offer(o: Offer, professor: User | None = None) -> dict:
    return {
        "id": o.id, "request_id": o.request_id, "professor_id": o.professor_id,
        "professor_name": professor.display_name if professor else None,
        "message": o.message, "conditions": o.conditions, "status": o.status,
        "created_at": iso(o.created_at),
    }


def ser_message(m: Message, sender: User | None = None, att: Attachment | None = None) -> dict:
    return {
        "id": m.id, "conversation_id": m.conversation_id, "sender_id": m.sender_id,
        "sender_name": sender.display_name if sender else None,
        "kind": m.kind, "body": m.body,
        "attachment": {"id": att.id, "orig_name": att.orig_name, "size": att.size} if att else None,
        "created_at": iso(m.created_at),
    }


def ser_conversation(c: Conversation, student: User | None, professor: User | None, request_title: str = "") -> dict:
    return {
        "id": c.id, "request_id": c.request_id, "request_title": request_title,
        "student_id": c.student_id, "student_name": student.display_name if student else None,
        "professor_id": c.professor_id, "professor_name": professor.display_name if professor else None,
        "created_at": iso(c.created_at),
    }


def ser_agreement(a: Agreement) -> dict:
    return {
        "id": a.id, "request_id": a.request_id, "offer_id": a.offer_id,
        "title": a.title, "responsibilities": a.responsibilities, "timeline": a.timeline,
        "deliverables": a.deliverables, "confidentiality": a.confidentiality,
        "ip_ownership": a.ip_ownership,
        "student_signed_at": iso(a.student_signed_at), "professor_signed_at": iso(a.professor_signed_at),
        "fully_signed": bool(a.student_signed_at and a.professor_signed_at),
        "created_at": iso(a.created_at),
    }


def ser_project(p: Project, lead: User | None = None, members=None, names=None) -> dict:
    member_list = members or []
    names = names or {}
    return {
        "id": p.id, "request_id": p.request_id, "title": p.title,
        "lead_professor_id": p.lead_professor_id,
        "lead_professor_name": lead.display_name if lead else None,
        "status": p.status, "closed_reason": p.closed_reason,
        "created_at": iso(p.created_at), "closed_at": iso(p.closed_at),
        "members": [
            {"user_id": m.user_id, "role": m.role,
             "name": names[m.user_id].display_name if m.user_id in names else None}
            for m in member_list
        ],
    }


def ser_task(t: ProjectTask, assignee: User | None = None) -> dict:
    return {
        "id": t.id, "project_id": t.project_id, "title": t.title, "description": t.description,
        "assignee_id": t.assignee_id, "assignee_name": assignee.display_name if assignee else None,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "status": t.status, "created_at": iso(t.created_at),
    }


def ser_meeting(m: ProjectMeeting) -> dict:
    return {
        "id": m.id, "project_id": m.project_id, "title": m.title,
        "scheduled_at": iso(m.scheduled_at), "minutes": m.minutes, "created_at": iso(m.created_at),
    }


def ser_report(r: ProgressReport, author: User | None = None) -> dict:
    return {
        "id": r.id, "project_id": r.project_id, "author_id": r.author_id,
        "author_name": author.display_name if author else None,
        "percent": r.percent, "note": r.note, "feedback": r.feedback, "created_at": iso(r.created_at),
    }


def ser_notification(n: Notification) -> dict:
    return {
        "id": n.id, "type": n.type, "title": n.title, "body": n.body, "link": n.link,
        "is_read": n.is_read, "created_at": iso(n.created_at),
    }


def ser_event(e: EventLog) -> dict:
    return {"id": e.id, "type": e.type, "actor_id": e.actor_id, "payload": e.payload or {}, "created_at": iso(e.created_at)}
