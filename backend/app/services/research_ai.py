"""دستیار هوشمند نگارش پژوهش — قاعده‌محور، صادق و متصل به لایهٔ معنایی.

هیچ ادعای «مدل زبانی صندوق سیاه» نداریم: خروجی‌ها با موتور نسخه‌دار (doc-ai-1.0.0)
از تحلیل آماری متن، اسکلت قالب‌های استاندارد و واژگان کنترل‌شدهٔ لایهٔ معنایی ساخته می‌شوند.
"""
import re
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.deps import get_current_user
from ..core.utils import log_event
from ..models import AiSuggestionLog, DocReference, DocSection, ResearchDoc, SemanticConcept, User
from .research import DOC_TEMPLATES, _doc, _template, _word_count, require_doc_access

router = APIRouter(prefix="/api/v1/ai", tags=["دستیار نگارش پژوهش"])

ENGINE = "doc-ai-1.0.0"
HONEST_NOTE = "خروجی قاعده‌محور و آزمایشی است؛ پیش‌نویس پایهٔ شماست و جای بازنویسی انسانی دارد."

_FA_STOPWORDS = {
    "و", "در", "به", "از", "که", "این", "با", "برای", "است", "می", "های", "را", "بر", "آن", "ها",
    "یک", "شده", "شد", "شود", "خواهد", "دارد", "بین", "هر", "نیز", "اما", "یا", "تا", "هم", "پس",
    "اگر", "چه", "کرد", "کردن", "داده", "دادهٔ", "شدهٔ", "باشد", "باید", "براساس", "بر اساس", "مورد",
    "نمونهٔ", "بخش", "داخل", "سایر", "کل", "حالت", "مثال", "مثل", "بسیار", "خیلی", "همه", "چند",
}
_EN_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "in", "on", "for", "to", "is", "are", "was", "were",
    "this", "that", "with", "as", "by", "it", "at", "from", "be", "been", "was", "we", "our",
    "their", "its", "can", "will", "has", "have", "had", "not", "but", "which", "into", "more",
}

# چک‌لیست مقصد بر پایهٔ قالب — از راهنمای هر نشریه
_VENUE_CHECKLIST = {
    "ieee-conference": ["ارقام و جدول‌ها در ستون مناسب و خوانا باشند", "ارجاع‌ها عددی و به سبک IEEE باشند",
                        "خلاصه بدون ارجاع باشد", "حجم معمولاً ۴ تا ۸ صفحهٔ دوستونه است"],
    "ieee-journal": ["بخش Reproducibility/پیاده‌سازی در صورت امکان اضافه شود", "نمادهای ریاضی یکدست تعریف شوند",
                     "ارجاع‌ها عددی و کامل باشند"],
    "springer-lncs": ["خلاصه بین ۱۵۰ تا ۲۵۰ کلمه", "ارجاع‌ها عددی به سبک LNCS", "کلیدواژه‌ها تا ۶ مورد"],
    "springer-article": ["ساختار IMRaD رعایت شود", "ارجاع نویسنده-سال یکدست باشد"],
    "apa-article": ["فاصلهٔ خطوط دوبرابر", "ارجاع نویسنده-سال داخل متن", "فهرست مراجع با تورفتگی آویز"],
    "fa-thesis": ["مطابق آیین‌نامهٔ نگارش دانشگاه", "مصدر به‌جای ماضی در متن علمی", "ارجاع داخل متن و فهرست منابع یکدست"],
}


def _sentences(text: str) -> list[str]:
    parts = re.split(r"[.؟!،؛;\n]+", text or "")
    return [p.strip() for p in parts if len(p.strip()) > 12]


def _tokens(text: str) -> list[str]:
    text = (text or "").lower().replace("ي", "ی").replace("ك", "ک")
    return [t for t in re.findall(r"[آ-یa-z0-9\u200c]{3,}", text)
            if t not in _FA_STOPWORDS and t not in _EN_STOPWORDS]


def _doc_sections(db: Session, doc_id: int) -> list[DocSection]:
    return db.query(DocSection).filter(DocSection.doc_id == doc_id).order_by(DocSection.ord).all()


def _refs(db: Session, doc_id: int) -> list[DocReference]:
    return db.query(DocReference).filter(DocReference.doc_id == doc_id).order_by(DocReference.id).all()


class DocIdIn(BaseModel):
    doc_id: int
    section_id: int | None = None


class OutlineIn(BaseModel):
    doc_id: int


def _log(db: Session, user: User, kind: str, inp: dict, out: dict):
    db.add(AiSuggestionLog(user_id=user.id, kind=kind, input_json=inp, output_json={"engine": ENGINE, **out}))
    db.commit()


@router.post("/doc-outline", summary="طرح‌وارهٔ نگارش سند بر پایهٔ قالب و پیشرفت فعلی")
def doc_outline(body: OutlineIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_doc_access(db, body.doc_id, user)
    d = _doc(db, body.doc_id)
    t = _template(d)
    sections = _doc_sections(db, body.doc_id)
    items = []
    for s in sections:
        words = _word_count(s.body)
        empty = words == 0
        items.append({
            "section_id": s.id, "heading": s.heading, "words": words, "state": "empty" if empty else "started",
            "guidance": s.guidance or "",
            "min_words_hint": 200 if s.heading.lower().startswith(("intro", "method", "مقدمه", "روش", "پیشینه")) else 120,
            "suggestion": (f"«{s.heading}» هنوز خالی است — با راهنمای قالب شروع کنید: {s.guidance}"
                           if empty else f"«{s.heading}» در جریان است؛ ادعاهای بدون ارجاع را تکمیل کنید."),
        })
    out = {"engine": ENGINE, "note": HONEST_NOTE, "template": d.template, "template_hint": t["venue_hint"],
           "citation_style": t["citation"], "progress": {
               "filled_sections": sum(1 for i in items if i["words"] > 0),
               "total_sections": len(items), "total_words": sum(i["words"] for i in items) + _word_count(d.abstract)},
           "items": items}
    _log(db, user, "doc_outline", {"doc_id": body.doc_id}, out)
    return out


@router.post("/doc-feedback", summary="بازخورد نگارش: آمار، ادعای بدون ارجاع، جملهٔ طولانی، تکرار")
def doc_feedback(body: DocIdIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_doc_access(db, body.doc_id, user)
    d = _doc(db, body.doc_id)
    t = _template(d)
    if body.section_id:
        sections = [s for s in _doc_sections(db, body.doc_id) if s.id == body.section_id]
        if not sections:
            raise HTTPException(status_code=404, detail="بخش یافت نشد")
    else:
        sections = _doc_sections(db, body.doc_id)
    issues, stats = [], {}
    cite_re = re.compile(r"(\[\d+\]|\(\d{4}\)|\bdoi\.org|\bORCID)")
    for s in sections:
        words = _word_count(s.body)
        stats[s.heading] = {"words": words, "sentences": len(_sentences(s.body))}
        if words == 0:
            issues.append(f"«{s.heading}» هنوز نوشته نشده است")
            continue
        for para in [p for p in s.body.split("\n") if p.strip()]:
            pw = _word_count(para)
            if pw < 12:
                continue
            if not cite_re.search(para) and s.heading.lower().startswith(
                    ("related", "literature", "پیشینه", "مقدمه")):
                issues.append(f"در «{s.heading}» پاراگراف بدون ارجاع دارید: «{para[:60]}…»")
            for sent in _sentences(para):
                if _word_count(sent) > 45:
                    issues.append(f"جملهٔ بسیار طولانی در «{s.heading}» ({_word_count(sent)} واژه) — بشکنید: «{sent[:60]}…»")
        if words < 60 and not s.heading.lower().startswith(("abstract", "چکیده", "نتیجه", "conclusion")):
            issues.append(f"«{s.heading}» کوتاه است ({words} واژه) — حداقل ۶۰ واژه پیشنهاد می‌شود")
    tf = Counter(tok for s in sections for tok in _tokens(s.body))
    repeated = [w for w, c in tf.most_common(5) if c >= 8]
    if repeated:
        issues.append("واژه‌های پرتکرار (در صورت لازم با مترادف جایگزین کنید): " + "، ".join(repeated))
    out = {"engine": ENGINE, "note": HONEST_NOTE, "stats": stats,
           "total_words": sum(v["words"] for v in stats.values()),
           "issues": issues[:20], "venue_checklist": _VENUE_CHECKLIST.get(d.template, [])}
    _log(db, user, "doc_feedback", {"doc_id": body.doc_id, "section_id": body.section_id}, out)
    return out


@router.post("/doc-abstract", summary="پیش‌نویس انتزاعی چکیده از متن بخش‌ها (استخراجی و شفاف)")
def doc_abstract(body: OutlineIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_doc_access(db, body.doc_id, user)
    d = _doc(db, body.doc_id)
    t = _template(d)
    fa = d.language == "fa"
    sections = _doc_sections(db, body.doc_id)
    tf = Counter(tok for s in sections for tok in _tokens(s.body))
    scored = []
    for s in sections:
        head = s.heading.lower()
        weight = 1.5 if any(k in head for k in ("intro", "method", "result", "conclusion", "مقدمه", "روش", "یافته", "نتیجه")) else 1.0
        for pos, sent in enumerate(_sentences(s.body)):
            toks = _tokens(sent)
            if not toks:
                continue
            score = (sum(tf[x] for x in toks) / len(toks)) * weight + (0.5 if pos == 0 else 0)
            scored.append({"heading": s.heading, "sentence": sent, "score": round(score, 2)})
    scored.sort(key=lambda x: -x["score"])
    picked = scored[:6]
    out = {"engine": ENGINE, "note": HONEST_NOTE,
           "abstract_scaffold": [f"[{p['heading']}] {p['sentence']}" for p in picked],
           "hint": ("جمله‌ها را به متن پیوسته بازنویسی کنید؛ ترتیب پیشنهادی: مسئله ← روش ← نتیجه ← اهمیت."
                    if fa else "Rewrite into one paragraph: problem → method → result → significance.")}
    if fa:
        opener = f"این پژوهش به مسئلهٔ «{d.title}» می‌پردازد. "
        out["abstract_draft"] = opener + " ".join(p["sentence"] for p in picked[:4])
    _log(db, user, "doc_abstract", {"doc_id": body.doc_id}, out)
    return out


@router.post("/doc-keywords", summary="پیشنهاد کلیدواژه از متن + اتصال به مفاهیم لایهٔ معنایی")
def doc_keywords(body: OutlineIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_doc_access(db, body.doc_id, user)
    d = _doc(db, body.doc_id)
    sections = _doc_sections(db, body.doc_id)
    tf = Counter(tok for s in sections for tok in _tokens(s.body) )
    top = [w for w, _ in tf.most_common(12)]
    existing = {k.lower() for k in (d.keywords or [])}
    suggestions = [w for w in top if w not in existing][:8]
    # تطبیق با واژگان کنترل‌شده — مترادف‌ها هم بررسی می‌شوند
    concepts = db.query(SemanticConcept).filter(SemanticConcept.status == "approved").all()
    linked = []
    for c in concepts:
        cands = {c.name_fa.lower(), c.name_en.lower(), *(s.lower() for s in (c.synonyms or []))}
        hit = next((w for w in top if w in cands), None)
        if hit:
            linked.append({"concept_id": c.id, "name_fa": c.name_fa, "name_en": c.name_en, "matched": hit})
    out = {"engine": ENGINE, "note": HONEST_NOTE, "suggestions": suggestions,
           "semantic_concepts": linked[:6],
           "message": (f"{len(linked)} مفهوم رسمی واژگان با متن سند مطابقت دارد؛ این کلیدواژه‌ها "
                       "در انتشار سند به مفاهیم لایهٔ معنایی پیوند می‌خورند." if linked else
                       "هنوز تطابق با واژگان کنترل‌شده پیدا نشد؛ از فهرست مفاهیم صفحهٔ شبکهٔ دانش کمک بگیرید.")}
    _log(db, user, "doc_keywords", {"doc_id": body.doc_id}, out)
    return out


@router.post("/doc-related-work", summary="اسکلت پیشینهٔ پژوهش از مرجع‌های ثبت‌شده + شاخص‌های قالب")
def doc_related_work(body: OutlineIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_doc_access(db, body.doc_id, user)
    d = _doc(db, body.doc_id)
    refs = _refs(db, body.doc_id)
    fa = d.language == "fa"
    by_year = {}
    for r in refs:
        by_year.setdefault(r.year or "بدون تاریخ", []).append(r)
    scaffold = []
    if refs:
        for year in sorted(by_year):
            names = "؛ ".join(r.authors.split(",")[0] for r in by_year[year][:3])
            scaffold.append(f"[{year}] — {names}: مرور و مقایسه با کار شما؛ ارجاع: "
                            + "، ".join(f"[{i}]" for i, r in enumerate(refs, 1) if r in by_year[year]))
    else:
        scaffold.append(f"{'هنوز مرجعی ثبت نشده؛ حداقل ۸ مرجع مرتبط اضافه کنید' if fa else 'Add at least 8 relevant references'}")
    out = {"engine": ENGINE, "note": HONEST_NOTE, "reference_count": len(refs),
           "scaffold": scaffold,
           "structure_hint": ("الگوی پیشنهادی هر پاراگراف: موضوع‌بندی (نه فهرست مقاله‌به‌مقاله)، "
                              "مقایسه با کار خودتان، ارجاع عددی در پایان جمله." if fa else
                              "Theme-based paragraphs, contrast with your work, numeric citations at sentence end."),
           "gaps": ["چه شکافی میان کارهای پیشین و مسئلهٔ شما هست؟",
                    "کدام روش پیشین نزدیک‌ترین است و تفاوت شما چیست؟"] if fa else
                   ["What gap do prior works leave for your problem?",
                    "Which prior method is closest, and how do you differ?"]}
    _log(db, user, "doc_related_work", {"doc_id": body.doc_id}, out)
    return out