"""فضای پژوهش تیمی — نگارش مشترک سند پژوهشی دانشجو و استاد با نقش‌ها، نسخه‌ها،
مرجع‌ها، قالب‌های استاندارد (IEEE، اسپرینگر، APA، پایان‌نامهٔ فارسی) و خروجی tex/docx/html.
"""
import io
import re
import uuid
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, require_roles
from ..core.database import get_db
from ..core.utils import log_event, notify, now_utc
from ..models import (
    DocComment, DocMember, DocReference, DocSection, DocVersion, Project, ResearchDoc, User,
)

router = APIRouter(prefix="/api/v1/research", tags=["فضای پژوهش تیمی"])

DOC_STATUSES = {
    "draft": "پیش‌نویس",
    "in_review": "در حال داوری داخلی",
    "revised": "بازنویسی‌شده",
    "approved": "تأیید مسئول سند",
    "published": "منتشرشده در شبکهٔ دانش",
}
# گذارهای مجاز وضعیت سند: action → (from_states, to_state, فقط_مسئول)
DOC_TRANSITIONS = {
    "submit_review": (["draft", "revised"], "in_review", False),
    "mark_revised": (["in_review"], "revised", False),
    "approve": (["revised", "in_review"], "approved", True),
    "reopen": (["in_review", "revised", "approved"], "draft", True),
}

DOC_ROLES = {
    "lead": "مسئول سند",
    "writer": "نویسنده",
    "reviewer": "داور داخلی",
    "observer": "ناظر",
}

# ============================================================
# قالب‌های استاندارد — اسکلت بخش‌ها + سبک ارجاع + پیش‌خوان LaTeX
# برچسب صادقانه: «قالب سبک X» یعنی ساختار و ترتیب بخش‌ها مطابق
# راهنمای نشریه؛ فایل نهایی رسمی باید با کلاس رسمی نشریه ترجمه شود.
# ============================================================

DOC_TEMPLATES = {
    "ieee-conference": {
        "title": "IEEE — کنفرانس (دوستونه)",
        "language": "en", "citation": "numeric-ieee", "columns": 2,
        "tex_class": "\\documentclass[conference]{IEEEtran}",
        "venue_hint": "کنفرانس‌های IEEE؛ US Letter، دو ستونه، ارجاع عددی [۱]، معمولاً ۴–۸ صفحه.",
        "sections": [
            ("Abstract", "خلاصهٔ ۱۵۰–۲۵۰ کلمه‌ای: مسئله، روش، نتیجهٔ کلیدی، اهمیت."),
            ("Introduction", "انگیزه، شکاف پژوهشی، سؤال/هدف، فهرست مشارکت‌ها."),
            ("Related Work", "مقایسهٔ روش‌های پیشین و تمایز کار شما؛ هر پاراگراف ارجاع."),
            ("Methodology", "رویکرد، مدل ریاضی/الگوریتم، فرضیات."),
            ("Experiments and Results", "مجموعه‌داده، سنجه‌ها، جدول نتایج، تحلیل."),
            ("Conclusion and Future Work", "جمع‌بندی + محدودیت‌ها + مسیر آینده."),
        ],
    },
    "ieee-journal": {
        "title": "IEEE — مجله",
        "language": "en", "citation": "numeric-ieee", "columns": 2,
        "tex_class": "\\documentclass[journal]{IEEEtran}",
        "venue_hint": "مجلات IEEE؛ ساختار مشابه کنفرانس با بخش Verification/Reproducibility در صورت نیاز.",
        "sections": [
            ("Abstract", "خلاصهٔ جامع با کمی نتایج کمّی."),
            ("Introduction", "زمینه، مسئله، مشارکت‌ها، ساختار مقاله."),
            ("Related Work", "مرور نظام‌مندتر نسبت به کنفرانس؛ جدول مقایسه پیشنهاد می‌شود."),
            ("Proposed Method", "روش پیشنهادی با قلم‌بندی کامل نمادها."),
            ("Experimental Evaluation", "طراحی آزمایش، پایگاه‌داده، سنجه، نتایج و بحث."),
            ("Conclusion", "جمع‌بندی و کارهای آینده."),
        ],
    },
    "springer-lncs": {
        "title": "اسپرینگر — LNCS (شورشویر علوم رایانه)",
        "language": "en", "citation": "numeric-springer", "columns": 1,
        "tex_class": "\\documentclass{llncs}",
        "venue_hint": "سری LNCS/LNAI؛ تک‌ستونه، ۱۲–۱۵ صفحه، ارجاع عددی، کلاس رسمی llncs.cls.",
        "sections": [
            ("Abstract", "خلاصهٔ ۱۵۰–۲۵۰ کلمه‌ای بدون ارجاع."),
            ("Introduction", "مسئله و مشارکت."),
            ("Related Work", "پیشینهٔ مرتبط."),
            ("Method", "روش پیشنهادی."),
            ("Evaluation", "ارزیابی تجربی."),
            ("Conclusion", "نتیجه‌گیری."),
        ],
    },
    "springer-article": {
        "title": "اسپرینگر — مقالهٔ مجله (سبک Springer)",
        "language": "en", "citation": "author-year-springer", "columns": 1,
        "tex_class": "\\documentclass[smallextended]{svjour3}",
        "venue_hint": "قالب سبک مجلات اسپرینگر؛ کلاس رسمی svjour3 و پارامترهای مجلهٔ مقصد را از راهنمای همان مجله بگیرید.",
        "sections": [
            ("Abstract", "خلاصهٔ ساختاریافتهٔ کوتاه."),
            ("Introduction", "زمینه و سؤال پژوهش."),
            ("Literature Review", "مرور ادبیات با ارجاع نویسنده-سال."),
            ("Materials and Methods", "داده، روش، تحلیل."),
            ("Results and Discussion", "یافته‌ها و بحث."),
            ("Conclusion", "نتیجه‌گیری و دلالت‌ها."),
        ],
    },
    "apa-article": {
        "title": "APA 7 — دست‌نویس مقاله",
        "language": "en", "citation": "author-year-apa", "columns": 1,
        "tex_class": "\\documentclass[12pt]{article} % + apacite / biblatex-apa",
        "venue_hint": "سبک APA ویرایش هفتم؛ فاصلهٔ خطوط دوبرابر، ارجاع نویسنده-سال، فهرست مراجع با تورفتگی آویز.",
        "sections": [
            ("Abstract", "خلاصهٔ ۱۵۰–۲۵۰ کلمه‌ای."),
            ("Introduction", "معرفی مسئله و فرضیه‌ها."),
            ("Literature Review", "مرور منابع."),
            ("Method", "شرکت‌کنندگان، ابزار، رویه."),
            ("Results", "یافته‌ها."),
            ("Discussion", "تفسیر، محدودیت، دلالت."),
        ],
    },
    "fa-thesis": {
        "title": "پایان‌نامه / رسالهٔ فارسی",
        "language": "fa", "citation": "numeric-fa", "columns": 1,
        "tex_class": "\\documentclass{book} % XePersian: \\usepackage{xepersian} و \\settextfont{Vazirmatn}",
        "venue_hint": "قالب فارسی راست‌به‌چپ؛ مطابق آیین‌نامهٔ نگارش دانشگاه، کامپایل با XeLaTeX.",
        "sections": [
            ("چکیده", "خلاصهٔ ۲۵۰ کلمه‌ای فارسی + کلیدواژه‌ها."),
            ("مقدمه", "بیان مسئله، اهداف، سؤال‌ها، ساختار پایان‌نامه."),
            ("پیشینهٔ پژوهش", "مرور مطالعات داخلی و خارجی با ارجاع."),
            ("روش پژوهش", "جامعه، نمونه، ابزار، روش تحلیل."),
            ("یافته‌های پژوهش", "نتایج تحلیل و جداول."),
            ("بحث و نتیجه‌گیری", "تفسیر یافته‌ها، محدودیت‌ها، پیشنهادها."),
            ("منابع", "فهرست منابع به شیوهٔ مورد تأیید دانشگاه."),
        ],
    },
}

CITATION_STYLES = ("ieee", "springer", "apa")


def _template(doc: ResearchDoc) -> dict:
    t = DOC_TEMPLATES.get(doc.template)
    if not t:
        raise HTTPException(status_code=400, detail="قالب نامعتبر است")
    return t


def _doc(db: Session, doc_id: int) -> ResearchDoc:
    d = db.get(ResearchDoc, doc_id)
    if not d:
        raise HTTPException(status_code=404, detail="سند پژوهشی یافت نشد")
    return d


def _member(db: Session, doc_id: int, user_id: int) -> DocMember | None:
    return db.query(DocMember).filter(DocMember.doc_id == doc_id, DocMember.user_id == user_id).one_or_none()


def require_doc_access(db: Session, doc_id: int, user: User, min_role: str | None = None) -> DocMember | None:
    """کنترل دسترسی: عضو سند یا مدیر؛ min_role ناظر<داور<نویسنده<مسئول"""
    rank = {"observer": 0, "reviewer": 1, "writer": 2, "lead": 3}
    d = _doc(db, doc_id)
    m = _member(db, doc_id, user.id)
    if m:
        if min_role and rank.get(m.role, 0) < rank[min_role]:
            raise HTTPException(status_code=403, detail=f"این عملیات نقش {DOC_ROLES[min_role]} را لازم دارد")
        return m
    if set(user.roles or []) & {"research_manager", "system_admin"}:
        return None
    raise HTTPException(status_code=403, detail="فقط اعضای فضای پژوهش به این سند دسترسی دارند")


def ser_doc(d: ResearchDoc, owner: User | None, members: list[DocMember] | None = None, umap: dict | None = None):
    umap = umap or {}
    return {
        "id": d.id, "title": d.title, "language": d.language, "template": d.template,
        "template_title": DOC_TEMPLATES.get(d.template, {}).get("title", d.template),
        "status": d.status, "status_fa": DOC_STATUSES.get(d.status, d.status),
        "abstract": d.abstract, "keywords": d.keywords or [], "venue_note": d.venue_note,
        "owner_id": d.owner_id, "owner_name": owner.display_name if owner else "",
        "project_id": d.project_id, "semantic_entity_id": d.semantic_entity_id,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "members": [{"id": m.id, "user_id": m.user_id, "name": umap.get(m.user_id, User(display_name="?")).display_name,
                     "role": m.role, "role_fa": DOC_ROLES.get(m.role, m.role)} for m in (members or [])],
    }


def _member_umap(db: Session, doc_id: int) -> dict[int, User]:
    out = {}
    for m in db.query(DocMember).filter(DocMember.doc_id == doc_id).all():
        u = db.get(User, m.user_id)
        if u:
            out[m.user_id] = u
    return out


# ---------- ورودی‌ها ----------

class DocIn(BaseModel):
    title: str
    template: str = "ieee-conference"
    language: str = ""          # خالی = از قالب
    project_id: int | None = None
    venue_note: str = ""


class DocPatch(BaseModel):
    title: str | None = None
    template: str | None = None
    venue_note: str | None = None
    abstract: str | None = None
    keywords: list[str] | None = None
    action: str | None = None   # گذار وضعیت


class MemberIn(BaseModel):
    username: str
    role: str = "writer"


class SectionIn(BaseModel):
    heading: str = ""
    body: str = ""


class SectionPatch(BaseModel):
    heading: str | None = None
    body: str | None = None
    ord: int | None = None
    assigned_to: int | None = None
    base_version_no: int | None = None   # قفل خوش‌بینانه


class VersionIn(BaseModel):
    label: str = ""


class CommentIn(BaseModel):
    section_id: int | None = None
    body: str


class RefIn(BaseModel):
    authors: str = ""
    title: str
    venue: str = ""
    year: str = ""
    doi: str = ""
    url: str = ""
    note: str = ""


# ---------- اندپوینت‌های سند ----------

@router.get("/templates", summary="فهرست قالب‌های استاندارد سند پژوهشی")
def templates():
    return [{"key": k, "title": v["title"], "language": v["language"], "citation": v["citation"],
             "columns": v["columns"], "venue_hint": v["venue_hint"],
             "sections": [{"heading": h, "guidance": g} for h, g in v["sections"]]}
            for k, v in DOC_TEMPLATES.items()]


@router.post("/docs", summary="ایجاد فضای پژوهش جدید با اسکلت قالب")
def create_doc(body: DocIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="عنوان سند الزامی است")
    t = DOC_TEMPLATES.get(body.template)
    if not t:
        raise HTTPException(status_code=400, detail="قالب نامعتبر است")
    if body.project_id and not db.get(Project, body.project_id):
        raise HTTPException(status_code=404, detail="پروژهٔ مقصد یافت نشد")
    d = ResearchDoc(owner_id=user.id, title=body.title.strip(), template=body.template,
                    language=body.language or t["language"], project_id=body.project_id,
                    venue_note=body.venue_note)
    db.add(d)
    db.flush()
    db.add(DocMember(doc_id=d.id, user_id=user.id, role="lead", added_by=user.id))
    for i, (heading, guidance) in enumerate(t["sections"], start=1):
        db.add(DocSection(doc_id=d.id, ord=i, heading=heading, guidance=guidance))
    log_event(db, "research_doc_created", user.id, {"doc_id": d.id, "template": d.template})
    db.commit()
    return ser_doc(d, user, db.query(DocMember).filter(DocMember.doc_id == d.id).all(),
                   {user.id: user})


@router.get("/docs/mine", summary="سندهای من (عضو هر نقشی)")
def my_docs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(ResearchDoc, User).join(User, User.id == ResearchDoc.owner_id)
            .join(DocMember, DocMember.doc_id == ResearchDoc.id)
            .filter(DocMember.user_id == user.id).distinct()
            .order_by(ResearchDoc.updated_at.desc()).all())
    out = []
    for d, owner in rows:
        n_members = db.query(DocMember).filter(DocMember.doc_id == d.id).count()
        out.append({**ser_doc(d, owner), "member_count": n_members})
    return out


@router.get("/docs/all", summary="همهٔ سندها (مدیر پژوهش)")
def all_docs(user: User = Depends(require_roles("research_manager", "system_admin")),
             db: Session = Depends(get_db)):
    rows = (db.query(ResearchDoc, User).join(User, User.id == ResearchDoc.owner_id)
            .order_by(ResearchDoc.updated_at.desc()).limit(300).all())
    return [{**ser_doc(d, owner)} for d, owner in rows]


@router.get("/docs/{doc_id}", summary="نمای کامل سند: بخش‌ها، اعضا، مرجع‌ها، نسخه‌ها، گفت‌وگو")
def get_doc(doc_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    me = require_doc_access(db, doc_id, user)
    d = _doc(db, doc_id)
    umap = _member_umap(db, doc_id)
    members = db.query(DocMember).filter(DocMember.doc_id == doc_id).all()
    sections = db.query(DocSection).filter(DocSection.doc_id == doc_id).order_by(DocSection.ord).all()
    refs = db.query(DocReference).filter(DocReference.doc_id == doc_id).order_by(DocReference.id).all()
    versions = (db.query(DocVersion).filter(DocVersion.doc_id == doc_id)
                .order_by(DocVersion.created_at.desc()).limit(50).all())
    comments = (db.query(DocComment).filter(DocComment.doc_id == doc_id)
                .order_by(DocComment.created_at).all())
    return {
        **ser_doc(d, umap.get(d.owner_id), members, umap),
        "my_user_id": user.id,
        "my_role": me.role if me else ("reviewer" if set(user.roles or []) & {"research_manager", "system_admin"} else None),
        "sections": [_ser_section(s, umap) for s in sections],
        "references": [_ser_ref(r) for r in refs],
        "versions": [{"id": v.id, "label": v.label, "created_by": umap.get(v.created_by).display_name if umap.get(v.created_by) else "",
                      "created_at": v.created_at.isoformat() if v.created_at else None,
                      "words": v.snapshot.get("words", 0)} for v in versions],
        "comments": [{"id": c.id, "section_id": c.section_id, "body": c.body, "resolved": c.resolved,
                      "author": umap.get(c.author_id).display_name if umap.get(c.author_id) else "",
                      "created_at": c.created_at.isoformat() if c.created_at else None} for c in comments],
    }


def _ser_section(s: DocSection, umap: dict[int, User]):
    return {"id": s.id, "ord": s.ord, "heading": s.heading, "body": s.body, "guidance": s.guidance,
            "assigned_to": s.assigned_to, "assigned_name": umap[s.assigned_to].display_name if s.assigned_to in umap else "",
            "updated_by": s.updated_by, "updated_name": umap[s.updated_by].display_name if s.updated_by in umap else "",
            "version_no": s.version_no,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None}


def _ser_ref(r: DocReference):
    return {"id": r.id, "authors": r.authors, "title": r.title, "venue": r.venue,
            "year": r.year, "doi": r.doi, "url": r.url, "note": r.note}


@router.patch("/docs/{doc_id}", summary="ویرایش سند / گذار وضعیت")
def patch_doc(doc_id: int, body: DocPatch, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    m = require_doc_access(db, doc_id, user, min_role="writer")
    d = _doc(db, doc_id)
    if body.title is not None:
        if not body.title.strip():
            raise HTTPException(status_code=400, detail="عنوان نمی‌تواند خالی باشد")
        d.title = body.title.strip()
    if body.template is not None:
        if body.template not in DOC_TEMPLATES:
            raise HTTPException(status_code=400, detail="قالب نامعتبر است")
        d.template = body.template
    if body.venue_note is not None:
        d.venue_note = body.venue_note
    if body.abstract is not None:
        d.abstract = body.abstract
    if body.keywords is not None:
        d.keywords = [k.strip() for k in body.keywords if k.strip()][:15]
    if body.action:
        tr = DOC_TRANSITIONS.get(body.action)
        if not tr or d.status not in tr[0]:
            raise HTTPException(status_code=400, detail="این گذار وضعیت از وضعیت فعلی مجاز نیست")
        if tr[2] and (not m or m.role != "lead"):
            raise HTTPException(status_code=403, detail="این گذار فقط با مسئول سند انجام می‌شود")
        d.status = tr[1]
        log_event(db, f"research_doc_{body.action}", user.id, {"doc_id": doc_id, "status": d.status})
        for mem in db.query(DocMember).filter(DocMember.doc_id == doc_id, DocMember.user_id != user.id).all():
            notify(db, mem.user_id, "research", "وضعیت سند پژوهشی تغییر کرد",
                   f"«{d.title}» → {DOC_STATUSES[d.status]}", f"/research/{d.id}")
    db.commit()
    return ser_doc(d, db.get(User, d.owner_id))


# ---------- اعضای تیم ----------

@router.post("/docs/{doc_id}/members", summary="افزودن عضو تیم نگارش (مسئول سند)")
def add_member(doc_id: int, body: MemberIn, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    m = require_doc_access(db, doc_id, user, min_role="lead")
    if m is None:
        raise HTTPException(status_code=403, detail="فقط مسئول سند عضو اضافه می‌کند")
    if body.role not in DOC_ROLES or body.role == "lead":
        raise HTTPException(status_code=400, detail="نقش باید writer، reviewer یا observer باشد")
    target = db.query(User).filter(User.username == body.username.strip().lower()).one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="کاربر با این نام کاربری یافت نشد")
    if _member(db, doc_id, target.id):
        raise HTTPException(status_code=409, detail="این کاربر قبلاً عضو سند است")
    db.add(DocMember(doc_id=doc_id, user_id=target.id, role=body.role, added_by=user.id))
    d = _doc(db, doc_id)
    notify(db, target.id, "research", "عضویت در فضای پژوهش",
           f"شما به نگارش سند «{d.title}» با نقش {DOC_ROLES[body.role]} دعوت شدید.", f"/research/{doc_id}")
    log_event(db, "research_doc_member_added", user.id, {"doc_id": doc_id, "member_id": target.id, "role": body.role})
    db.commit()
    return {"ok": True}


@router.patch("/docs/{doc_id}/members/{member_id}", summary="تغییر نقش عضو / حذف (مسئول سند)")
def patch_member(doc_id: int, member_id: int, body: MemberIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    m = require_doc_access(db, doc_id, user, min_role="lead")
    target = db.get(DocMember, member_id)
    if not target or target.doc_id != doc_id or target.role == "lead":
        raise HTTPException(status_code=404, detail="عضو یافت نشد")
    if body.role in DOC_ROLES and body.role != "lead":
        target.role = body.role
    elif body.role == "remove":
        db.delete(target)
    else:
        raise HTTPException(status_code=400, detail="نقش نامعتبر است")
    db.commit()
    return {"ok": True}


# ---------- بخش‌های سند ----------

@router.post("/docs/{doc_id}/sections", summary="افزودن بخش جدید")
def add_section(doc_id: int, body: SectionIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    require_doc_access(db, doc_id, user, min_role="writer")
    max_ord = (db.query(DocSection).filter(DocSection.doc_id == doc_id)
               .order_by(DocSection.ord.desc()).first())
    s = DocSection(doc_id=doc_id, ord=(max_ord.ord + 1 if max_ord else 1),
                   heading=body.heading, body=body.body)
    db.add(s)
    db.commit()
    return _ser_section(s, _member_umap(db, doc_id))


@router.patch("/docs/{doc_id}/sections/{section_id}", summary="ویرایش بخش — با قفل خوش‌بینانه (version_no)")
def patch_section(doc_id: int, section_id: int, body: SectionPatch,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = require_doc_access(db, doc_id, user, min_role="writer")
    s = db.get(DocSection, section_id)
    if not s or s.doc_id != doc_id:
        raise HTTPException(status_code=404, detail="بخش یافت نشد")
    if body.base_version_no is not None and body.base_version_no != s.version_no:
        raise HTTPException(status_code=409, detail={
            "message": "این بخش هم‌زمان توسط عضو دیگری ویرایش شده است؛ نسخهٔ تازه را بگیرید",
            "current_version_no": s.version_no, "current_body": s.body})
    if body.heading is not None:
        s.heading = body.heading
    if body.body is not None:
        s.body = body.body
    if body.ord is not None:
        s.ord = body.ord
    if body.assigned_to is not None and (not m or m.role == "lead"):
        s.assigned_to = body.assigned_to or None
    s.updated_by = user.id
    s.version_no += 1
    d = _doc(db, doc_id)
    if d.status == "approved":
        d.status = "revised"   # هر تغییر پس از تأیید، سند را به بازبینی برمی‌گرداند
    db.commit()
    return _ser_section(s, _member_umap(db, doc_id))


# ---------- نسخه‌های سند ----------

@router.post("/docs/{doc_id}/versions", summary="ثبت نسخهٔ فوری از کل سند")
def create_version(doc_id: int, body: VersionIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    require_doc_access(db, doc_id, user, min_role="reviewer")
    d = _doc(db, doc_id)
    sections = db.query(DocSection).filter(DocSection.doc_id == doc_id).order_by(DocSection.ord).all()
    snapshot = {"sections": [{"heading": s.heading, "body": s.body} for s in sections],
                "abstract": d.abstract, "keywords": d.keywords or [],
                "words": sum(_word_count(s.body) for s in sections) + _word_count(d.abstract)}
    v = DocVersion(doc_id=doc_id, label=body.label or f"نسخهٔ {now_utc().strftime('%Y-%m-%d %H:%M')} UTC",
                   snapshot=snapshot, created_by=user.id)
    db.add(v)
    log_event(db, "research_doc_version", user.id, {"doc_id": doc_id, "words": snapshot["words"]})
    db.commit()
    return {"id": v.id, "label": v.label, "words": snapshot["words"]}


@router.post("/docs/{doc_id}/versions/{version_id}/restore", summary="بازگردانی نسخه (مسئول سند)")
def restore_version(doc_id: int, version_id: int, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    m = require_doc_access(db, doc_id, user, min_role="lead")
    v = db.get(DocVersion, version_id)
    if not v or v.doc_id != doc_id:
        raise HTTPException(status_code=404, detail="نسخه یافت نشد")
    sections = db.query(DocSection).filter(DocSection.doc_id == doc_id).order_by(DocSection.ord).all()
    for i, snap in enumerate(v.snapshot.get("sections", [])):
        if i < len(sections):
            sections[i].heading = snap.get("heading", sections[i].heading)
            sections[i].body = snap.get("body", "")
            sections[i].version_no += 1
            sections[i].updated_by = user.id
    d = _doc(db, doc_id)
    d.abstract = v.snapshot.get("abstract", d.abstract)
    d.keywords = v.snapshot.get("keywords", d.keywords)
    d.status = "revised"
    db.commit()
    return {"ok": True}


# ---------- گفت‌وگوی داوری ----------

@router.post("/docs/{doc_id}/comments", summary="ثبت دیدگاه داوری روی سند یا بخش")
def add_comment(doc_id: int, body: CommentIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    require_doc_access(db, doc_id, user)   # همهٔ اعضا حتی ناظر می‌توانند دیدگاه بدهند
    if not body.body.strip():
        raise HTTPException(status_code=400, detail="متن دیدگاه خالی است")
    if body.section_id:
        s = db.get(DocSection, body.section_id)
        if not s or s.doc_id != doc_id:
            raise HTTPException(status_code=404, detail="بخش یافت نشد")
    c = DocComment(doc_id=doc_id, section_id=body.section_id, author_id=user.id, body=body.body.strip())
    db.add(c)
    d = _doc(db, doc_id)
    if d.owner_id != user.id:
        notify(db, d.owner_id, "research", "دیدگاه داوری جدید", f"{user.display_name}: {c.body[:100]}", f"/research/{doc_id}")
    db.commit()
    return {"id": c.id, "author": user.display_name,
            "created_at": c.created_at.isoformat() if c.created_at else None}


@router.post("/docs/{doc_id}/comments/{comment_id}/resolve", summary="علامت‌گذاری دیدگاه به‌عنوان حل‌شده")
def resolve_comment(doc_id: int, comment_id: int, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    m = require_doc_access(db, doc_id, user, min_role="writer")
    c = db.get(DocComment, comment_id)
    if not c or c.doc_id != doc_id:
        raise HTTPException(status_code=404, detail="دیدگاه یافت نشد")
    c.resolved = not c.resolved
    db.commit()
    return {"id": c.id, "resolved": c.resolved}


# ---------- مرجع‌ها و فرمت‌بندی ----------

@router.post("/docs/{doc_id}/references", summary="افزودن مرجع کتاب‌شناختی")
def add_reference(doc_id: int, body: RefIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    require_doc_access(db, doc_id, user, min_role="writer")
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="عنوان مرجع الزامی است")
    if body.doi and not re.match(r"^10\.\d{4,9}/\S+$", body.doi.strip()):
        raise HTTPException(status_code=400, detail="قالب DOI معتبر نیست (مثال: 10.1109/5.771073)")
    r = DocReference(doc_id=doc_id, authors=body.authors.strip(), title=body.title.strip(),
                     venue=body.venue.strip(), year=body.year.strip(), doi=body.doi.strip(),
                     url=body.url.strip(), note=body.note, added_by=user.id)
    db.add(r)
    db.commit()
    return _ser_ref(r)


@router.delete("/docs/{doc_id}/references/{ref_id}", summary="حذف مرجع")
def delete_reference(doc_id: int, ref_id: int, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    require_doc_access(db, doc_id, user, min_role="writer")
    r = db.get(DocReference, ref_id)
    if not r or r.doc_id != doc_id:
        raise HTTPException(status_code=404, detail="مرجع یافت نشد")
    db.delete(r)
    db.commit()
    return {"ok": True}


@router.get("/docs/{doc_id}/references/formatted", summary="فرمت‌بندی مرجع‌ها به سبک IEEE/اسپرینگر/APA")
def format_references(doc_id: int, style: str = "ieee", user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    require_doc_access(db, doc_id, user)
    if style not in CITATION_STYLES:
        raise HTTPException(status_code=400, detail="سبک باید ieee، springer یا apa باشد")
    refs = db.query(DocReference).filter(DocReference.doc_id == doc_id).order_by(DocReference.id).all()
    return {"style": style,
            "items": [{"id": r.id, "index": i, "formatted": format_reference(r, style, i)}
                      for i, r in enumerate(refs, start=1)]}


def format_reference(r: DocReference, style: str, index: int) -> str:
    """فرمت‌بندی صادقانه بر پایهٔ فیلدهای ثبت‌شده — نویسندگان همان‌طور که ثبت شده می‌مانند."""
    authors = r.authors or "نویسندهٔ نامشخص"
    year = r.year or "بدون تاریخ"
    doi = f" https://doi.org/{r.doi}" if r.doi else ""
    if style == "ieee":
        return f"[{index}] {authors}, \u201c{r.title},\u201d {r.venue or 'منبع نامشخص'}, {year}.{doi}"
    if style == "springer":
        return f"{authors} ({year}). {r.title}. {r.venue or ''}.{doi}".replace("..", ".").strip()
    # apa
    return f"{authors} ({year}). {r.title}. {r.venue or ''}.{doi}".replace("..", ".").strip()


def _word_count(text: str) -> int:
    return len([w for w in re.split(r"\s+", (text or "").strip()) if w])


# ============================================================
# خروجی قالب‌ها: LaTeX (کلاس رسمی هر نشریه)، HTML چاپ‌آمیز، DOCX
# ============================================================

_TEX_ESC = {"\\": r"\textbackslash{}", "&": "\\&", "%": "\\%", "$": "\\$", "#": "\\#",
            "_": "\\_", "{": "\\{", "}": "\\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def _tex_escape(text: str) -> str:
    return "".join(_TEX_ESC.get(ch, ch) for ch in (text or ""))


def _build_tex(d: ResearchDoc, sections: list[DocSection], refs: list[DocReference], t: dict,
               names: list[str] | None = None) -> str:
    fa = d.language == "fa"
    lines = ["% خروجی خودکار پژوهشیار۳۶۰ — قالب: " + t["title"]]
    if fa:
        lines += ["% کامپایل با XeLaTeX؛ فونت فارسی لازم است"]
    lines += [t["tex_class"],
              "\\usepackage[utf8]{inputenc}" if not fa else "% XeLaTeX — inputenc لازم نیست",
              "\\usepackage{graphicx}", "\\usepackage{amsmath}", "\\usepackage{hyperref}"]
    if fa:
        lines += ["\\usepackage{xepersian}", "\\settextfont{Vazirmatn}"]
    lines += ["", f"\\title{{{ _tex_escape(d.title) }}}"]
    if names:
        lines.append("\\author{" + " \\and ".join(_tex_escape(a) for a in names) + "}")
    lines += ["\\maketitle", ""]
    if d.abstract:
        lines += ["\\begin{abstract}", _tex_escape(d.abstract), "\\end{abstract}", ""]
    for s in sections:
        lines += [f"\\section{{{ _tex_escape(s.heading) }}}"]
        body = (s.body or "").strip()
        lines.append(_tex_escape(body) if body else "% نوشته نشده")
        lines.append("")
    if refs:
        lines += ["\\begin{thebibliography}{99}"]
        for i, r in enumerate(refs, start=1):
            lines.append(f"\\bibitem{{ref{i}}} {_tex_escape(format_reference(r, 'ieee', i))}")
        lines += ["\\end{thebibliography}", ""]
    lines.append("\\end{document}")
    return "\n".join(lines)


_HTML_CSS = {
    "ieee-conference": "body{font-family:'Times New Roman',Times,serif;font-size:10pt;line-height:1.45;"
                       "column-count:2;column-gap:24px;margin:18mm;} h1{column-span:all;text-align:center;font-size:16pt;}"
                       "h2{font-size:10.5pt;text-transform:uppercase;text-align:center;margin:12px 0 4px;} .meta{column-span:all;text-align:center}",
    "ieee-journal":    "body{font-family:'Times New Roman',Times,serif;font-size:10pt;line-height:1.5;"
                       "column-count:2;column-gap:22px;margin:18mm;} h1{column-span:all;text-align:center;font-size:17pt;}"
                       "h2{font-size:11pt;margin:12px 0 4px;} .meta{column-span:all;text-align:center}",
    "springer-lncs":   "body{font-family:'Times New Roman',Times,serif;font-size:10pt;line-height:1.55;margin:22mm auto;max-width:7in;}"
                       "h1{font-size:15pt;text-align:left;} h2{font-size:12pt;margin:14px 0 4px;}",
    "springer-article":"body{font-family:Georgia,'Times New Roman',serif;font-size:11pt;line-height:1.6;margin:22mm auto;max-width:7.2in;}"
                       "h1{font-size:17pt;} h2{font-size:13pt;margin:16px 0 6px;}",
    "apa-article":     "body{font-family:'Times New Roman',Times,serif;font-size:12pt;line-height:2;margin:25mm;}"
                       "h1{text-align:center;font-size:13pt;} h2{font-size:12pt;font-weight:700;margin-top:18px;}"
                       "p{text-indent:1.5em;text-align:justify;}",
    "fa-thesis":       "body{font-family:Vazirmatn,'Vazir','Noto Naskh Arabic',sans-serif;font-size:12.5pt;line-height:2;"
                       "margin:24mm auto;max-width:7in;direction:rtl;} h1{text-align:center;} h2{margin:16px 0 8px;}"
                       "p{text-align:justify;}",
}


def _build_html(d: ResearchDoc, sections: list[DocSection], refs: list[DocReference], t: dict,
                names: list[str] | None = None) -> str:
    fa = d.language == "fa"
    css = _HTML_CSS.get(d.template, _HTML_CSS["springer-article"])
    esc = lambda s: (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    parts = [f"<!DOCTYPE html><html lang=\"{d.language}\"{' dir=\"rtl\"' if fa else ''}><head><meta charset='utf-8'>",
             "<meta name='viewport' content='width=device-width, initial-scale=1'>",
             f"<title>{esc(d.title)}</title><style>{css} .refs li{{margin-bottom:6px}} footer{{font-size:.8em;opacity:.7;margin-top:28px}}</style></head><body>",
             f"<h1>{esc(d.title)}</h1>",
             f"<div class='meta'>{' • '.join(esc(n) for n in (names or []))} — {esc(t['title'])}</div><hr>"]
    if d.abstract:
        parts.append(f"<h2>{'چکیده' if fa else 'Abstract'}</h2><p>{esc(d.abstract)}</p>")
        if d.keywords:
            parts.append(f"<p><b>{'کلیدواژه‌ها' if fa else 'Keywords'}:</b> {esc('، '.join(d.keywords))}</p>")
    for s in sections:
        if s.body or s.heading:
            parts.append(f"<h2>{esc(s.heading)}</h2>")
            for para in (s.body or "").split("\n"):
                if para.strip():
                    parts.append(f"<p>{esc(para)}</p>")
    if refs:
        parts.append(f"<h2>{'مراجع' if fa else 'References'}</h2><ol class='refs'>")
        for i, r in enumerate(refs, start=1):
            parts.append(f"<li>{esc(format_reference(r, 'ieee', i))}</li>")
        parts.append("</ol>")
    parts.append(f"<footer>{'خروجی خودکار پژوهشیار۳۶۰' if fa else 'Auto-generated by Pazhoheshyar360'} — {esc(t['title'])}</footer></body></html>")
    return "\n".join(parts)


def _build_docx(d: ResearchDoc, sections: list[DocSection], refs: list[DocReference], t: dict,
                names: list[str] | None = None) -> bytes:
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Pt

    fa = d.language == "fa"
    doc = docx.Document()

    def _rtl(p):
        if fa:
            pPr = p._p.get_or_add_pPr()
            bidi = pPr.makeelement(qn("w:bidi"), {})
            pPr.append(bidi)

    def _para(text, style=None, bold=False, center=False):
        p = doc.add_paragraph(style=style)
        run = p.add_run(text)
        if bold:
            run.bold = True
        if center:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _rtl(p)
        return p

    _para(d.title, style="Title", center=True)
    _para("، ".join(names or []), center=True)
    _para(t["title"], center=True)
    if d.abstract:
        _para("چکیده" if fa else "Abstract", style="Heading 1")
        _para(d.abstract)
        if d.keywords:
            _para(("کلیدواژه‌ها: " if fa else "Keywords: ") + "، ".join(d.keywords))
    for s in sections:
        _para(s.heading, style="Heading 1")
        for para in (s.body or "").split("\n"):
            if para.strip():
                _para(para)
    if refs:
        _para("مراجع" if fa else "References", style="Heading 1")
        for i, r in enumerate(refs, start=1):
            _para(format_reference(r, "ieee", i))
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@router.get("/docs/{doc_id}/export", summary="خروجی سند در قالب انتخابی — tex | html | docx")
def export_doc(doc_id: int, format: str = "tex", user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    require_doc_access(db, doc_id, user)
    d = _doc(db, doc_id)
    t = _template(d)
    sections = db.query(DocSection).filter(DocSection.doc_id == doc_id).order_by(DocSection.ord).all()
    refs = db.query(DocReference).filter(DocReference.doc_id == doc_id).order_by(DocReference.id).all()
    umap = _member_umap(db, doc_id)
    members = sorted(db.query(DocMember).filter(DocMember.doc_id == doc_id).all(),
                     key=lambda m: 0 if m.role == "lead" else 1)
    names = [umap[m.user_id].display_name for m in members if m.user_id in umap]
    if format == "tex":
        body = _build_tex(d, sections, refs, t, names)
        media, ext = "application/x-tex", "tex"
    elif format == "html":
        body = _build_html(d, sections, refs, t, names)
        media, ext = "text/html", "html"
    elif format == "docx":
        body = _build_docx(d, sections, refs, t, names)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ext = "docx"
    else:
        raise HTTPException(status_code=400, detail="فرمت باید tex، html یا docx باشد")
    log_event(db, "research_doc_exported", user.id, {"doc_id": doc_id, "format": format})
    db.commit()
    fname = f"research-doc-{doc_id}-{d.template}.{ext}"
    ascii_name = fname.encode("ascii", "ignore").decode() or f"research-doc-{doc_id}.{ext}"
    return Response(content=body, media_type=media,
                    headers={"Content-Disposition":
                             f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{fname}"})


# ============================================================
# انتشار سند در شبکهٔ دانش — اثر علمی + نویسندگی + نگاشت به مفاهیم
# ============================================================

@router.post("/docs/{doc_id}/publish", summary="انتشار سند در شبکهٔ دانش (مسئول سند، پس از تأیید)")
def publish_doc(doc_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = require_doc_access(db, doc_id, user, min_role="lead")
    if m is None:
        raise HTTPException(status_code=403, detail="فقط مسئول سند می‌تواند منتشر کند")
    d = _doc(db, doc_id)
    if d.status != "approved":
        raise HTTPException(status_code=400, detail="انتشار فقط پس از وضعیت «تأیید مسئول سند» ممکن است")
    from ..models import EntityIdentifier, RelationAssertion, SemanticEntity
    from .semantic import _uuid  # تولید شناسهٔ پایدار هم‌سان با لایهٔ معنایی

    stats = {"authors": 0, "concepts": 0}
    ent = None
    if d.semantic_entity_id:
        ent = db.get(SemanticEntity, d.semantic_entity_id)
    if not ent:
        ent = SemanticEntity(id=_uuid(), kind="Publication", ref_table="research_docs", ref_id=str(d.id),
                             display_name=d.title, summary=(d.abstract or "")[:400],
                             meta={"template": d.template, "language": d.language, "venue": d.venue_note,
                                   "keywords": d.keywords or []})
        db.add(ent)
        db.flush()
        d.semantic_entity_id = ent.id
        db.add(EntityIdentifier(entity_id=ent.id, scheme="internal", value=f"research_doc:{d.id}",
                                source_system="pazhoheshyar-core"))
    else:
        ent.display_name = d.title
        ent.summary = (d.abstract or "")[:400]

    # نویسندگی رسمی هر عضو (asserted) — اطمینان از عدم ثبت تکراری
    member_ids = {mm.user_id for mm in db.query(DocMember).filter(DocMember.doc_id == doc_id).all()}
    existing = {a.subject_entity_id for a in db.query(RelationAssertion).filter(
        RelationAssertion.predicate_code == "AUTHORED", RelationAssertion.object_entity_id == ent.id).all()}
    for uid in member_ids:
        person = _person_entity(db, uid)
        if person and person.id not in existing:
            db.add(RelationAssertion(id=_uuid(), subject_entity_id=person.id, predicate_code="AUTHORED",
                                     object_entity_id=ent.id, origin="asserted",
                                     source_system="pazhoheshyar-core", confidence=1.0,
                                     access_policy="internal", review_status="approved",
                                     payload={"role": "author"}))
            stats["authors"] += 1

    # نگاشت کلیدواژه‌ها به مفاهیم واژگان کنترل‌شده (extracted، در انتظار داوری)
    from ..models import SemanticConcept
    concepts = db.query(SemanticConcept).filter(SemanticConcept.status == "approved").all()
    linked_ids = {a.object_entity_id for a in db.query(RelationAssertion).filter(
        RelationAssertion.predicate_code == "ABOUT_FIELD", RelationAssertion.object_entity_id == ent.id).all()}
    for kw in (d.keywords or []):
        kw_n = _norm_fa(kw)
        for c in concepts:
            cands = {_norm_fa(c.name_fa), _norm_fa(c.name_en), *(_norm_fa(s) for s in (c.synonyms or []))}
            if kw_n and kw_n in cands and c.id not in linked_ids:
                db.add(RelationAssertion(id=_uuid(), subject_entity_id=ent.id, predicate_code="ABOUT_FIELD",
                                         object_entity_id=c.id, origin="extracted",
                                         source_system="pazhoheshyar-core", confidence=0.7,
                                         access_policy="internal", review_status="pending",
                                         rule_or_model_version="kw-1.0.0",
                                         payload={"keyword": kw}))
                stats["concepts"] += 1
                linked_ids.add(c.id)

    d.status = "published"
    log_event(db, "research_doc_published", user.id, {"doc_id": doc_id, "semantic_entity_id": ent.id, **stats})
    # رخداد خروجی برای سایر سامانه‌های اکوسیستم (semantic_outbox)
    log_event(db, "semantic_outbox", user.id,
              {"op": "upsert", "entity_id": ent.id, "kind": "Publication",
               "ref_table": "research_docs", "ref_id": str(d.id), "source": "research_workspace"})
    for mm in db.query(DocMember).filter(DocMember.doc_id == doc_id, DocMember.user_id != user.id).all():
        notify(db, mm.user_id, "research", "سند پژوهشی منتشر شد",
               f"«{d.title}» در شبکهٔ دانش ثبت شد.", f"/research/{doc_id}")
    db.commit()
    return {"ok": True, "semantic_entity_id": ent.id, **stats}


def _norm_fa(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().replace("ي", "ی").replace("ك", "ک")).lower()


def _person_entity(db: Session, user_id: int):
    """موجودیت شخص در شبکهٔ دانش (در صورت وجود از یکپارچه‌سازی) — در غیر این صورت ساخته می‌شود"""
    from ..models import EntityIdentifier, SemanticEntity as SE
    ref_val = f"users:{user_id}"
    ident = db.query(EntityIdentifier).filter(EntityIdentifier.scheme == "internal",
                                              EntityIdentifier.value == ref_val).one_or_none()
    if ident:
        return db.get(SE, ident.entity_id)
    u = db.get(User, user_id)
    if not u:
        return None
    p = db.query(SE).filter(SE.kind == "Person", SE.ref_table == "users", SE.ref_id == str(user_id)).one_or_none()
    if not p:
        p = SE(id=_uuid(), kind="Person", ref_table="users", ref_id=str(user_id),
               display_name=u.display_name, display_name_norm=_norm_fa(u.display_name))
        db.add(p)
        db.flush()
        db.add(EntityIdentifier(entity_id=p.id, scheme="internal", value=ref_val, source_system="pazhoheshyar-core"))
    return p


def _uuid() -> str:
    return str(uuid.uuid4())

