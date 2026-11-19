"""API لایه معنایی و گراف دانش — نقاط اتصال سند (بخش ۱۳).

الزامات رعایت‌شده: صفحه‌بندی/سقف نتایج، سقف عمق پیمایش، فیلترهای مجاز،
کنترل دسترسی در سطح رکورد، عملیات سنگین در پس‌زمینه با پاسخ آماری فوری.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.deps import get_current_user, require_roles
from ..models import User
from . import semantic as S

router = APIRouter(prefix="/api/v1/semantic", tags=["لایه معنایی و گراف دانش"])


# ------------------------------------------------ جست‌وجوی ترکیبی دانشگاه
@router.get("/search", summary="جست‌وجوی ترکیبی آگاه از مجوز (دقیق شناسه > نام > واژگانی > مفهوم)")
def search(q: str = "", types: str = "", limit: int = 20,
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return S.semantic_search(db, user, q, types=types, limit=limit)


# ------------------------------------------------ نمای کلی گراف
@router.get("/graph/overview", summary="نمای کلی شبکه دانش — فقط روابط مجاز کاربر")
def overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return S.graph_overview(db, user)


# ------------------------------------------------ موجودیت‌ها
@router.get("/entities/by-user/{user_id}", summary="موجودیت معنایی کاربر + خلاصهٔ پیوندها")
def entity_by_user(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    out = S.entity_by_user(db, user_id)
    if not out:
        raise HTTPException(status_code=404, detail="موجودیت معنایی برای این کاربر ساخته نشده است؛"
                                                    " پس از اجرای یکپارچه‌سازی داده در دسترس است.")
    return out


@router.get("/entities/{eid}", summary="مشاهده موجودیت مجاز با روابط فیلترشده بر سیاست دسترسی")
def entity_detail(eid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ent = S.resolve_entity(db, eid)
    if not ent:
        raise HTTPException(status_code=404, detail="موجودیت یافت نشد")
    S.rebuild_projection(db)
    import uuid as _u
    try:
        _u.UUID(eid)
    except ValueError:
        raise HTTPException(status_code=400, detail="شناسه موجودیت نامعتبر است")
    rels = []
    for e in S.visible_adj(user, ent.id):
        other = S._projection["ent"].get(e["other"], {})
        rels.append({"claim_id": e["claim_id"], "predicate": e["pred"],
                     "predicate_fa": S.PREDICATES[e["pred"]][0],
                     "origin": e["origin"], "origin_fa": S.ORIGIN_LABELS.get(e["origin"], e["origin"]),
                     "policy": e["policy"], "review_status": e["review"],
                     "confidence": e["conf"], "direction": e["dir"],
                     "other": {"id": other.get("id"), "kind": other.get("kind"),
                               "kind_fa": S.KIND_LABELS.get(other.get("kind"), ""),
                               "name": other.get("name")}})
    rels.sort(key=lambda r: (r["origin"], r["predicate"]))
    return {"id": ent.id, "kind": ent.kind, "kind_fa": S.KIND_LABELS.get(ent.kind, ent.kind),
            "name": ent.display_name, "summary": ent.summary,
            "meta": ent.meta or {}, "status": ent.status,
            "relations": rels, "projection_version": S._projection["version"],
            "note": "روابط استنتاجی (inferred) به معنای تخصص تأییدشده یا همکاری واقعی نیستند."}


@router.get("/entities/{eid}/neighborhood", summary="همسایگی محدود (عمق≤۲، سقف گره) با فیلتر سیاست")
def neighborhood(eid: str, depth: int = 1, limit: int = 30,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return S.neighborhood(db, user, eid, depth=depth, limit=limit)


@router.get("/entities/{eid}/provenance", summary="منشأ قابل نمایش ادعاهای موجودیت")
def provenance(eid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """منشأ — فقط ادعاهای مجاز کاربر؛ ادعاهای محرمانه شمرده می‌شوند نه نمایش."""
    from ..models import SourceRecord as SR
    ent = S.resolve_entity(db, eid)
    if not ent:
        raise HTTPException(status_code=404, detail="موجودیت یافت نشد")
    rows = db.query(S.RelationAssertion).filter(
        (S.RelationAssertion.subject_entity_id == ent.id) |
        (S.RelationAssertion.object_entity_id == ent.id)).all()
    hidden = 0
    out = []
    for cl in rows:
        edge = {"claim_id": cl.id, "pred": cl.predicate_code, "origin": cl.origin,
                "policy": cl.access_policy, "other": cl.object_entity_id
                if cl.subject_entity_id == ent.id else cl.subject_entity_id, "dir": "out"}
        if not S.can_view_claim(user, edge):
            hidden += 1
            continue
        out.append({"claim_id": cl.id, "predicate": cl.predicate_code,
                    "predicate_fa": S.PREDICATES.get(cl.predicate_code, (cl.predicate_code,))[0],
                    "origin": cl.origin, "origin_fa": S.ORIGIN_LABELS.get(cl.origin, cl.origin),
                    "source_system": cl.source_system, "confidence": cl.confidence,
                    "valid_from": str(cl.valid_from or ""), "valid_to": str(cl.valid_to or ""),
                    "observed_at": str(cl.observed_at or ""),
                    "review_status": cl.review_status,
                    "rule_or_model_version": cl.rule_or_model_version or ""})
    return {"entity_id": ent.id, "claims": out, "hidden_claims_count": hidden,
            "note": "منشأ هر ادعا به‌جای مقدار خام، منبع و نسخه را نشان می‌دهد؛ ادعاهای فیلترشده فقط شمرده می‌شوند."}


# ------------------------------------------------ پرس‌وجوی مسیر
class PathQuery(BaseModel):
    source_eid: str = Field(..., min_length=36, max_length=36)
    target_eid: str = Field(..., min_length=36, max_length=36)
    max_hops: int = Field(3, ge=1, le=4)


@router.post("/path-queries", summary="مسیرهای مجاز بین دو موجودیت (سقف عمق ۴، سقف مسیر)")
def path_queries(body: PathQuery, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return S.find_paths(db, user, body.source_eid, body.target_eid,
                        max_hops=body.max_hops, limit=5)


# ------------------------------------------------ واژگان کنترل‌شده
@router.get("/concepts", summary="واژگان کنترل‌شده (SKOS-سازگار) — نام دوزبانه، مترادف، سلسله‌مراتب")
def concepts(q: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from ..core.semantic_norm import normalize_text as N
    rows = db.query(S.SemanticConcept).all()
    out = []
    nq = N(q)
    for c in rows:
        if nq and nq not in N(c.name_fa) and nq not in N(c.name_en) \
                and not any(nq in N(s) for s in c.synonyms or []):
            continue
        out.append({"id": c.id, "name_fa": c.name_fa, "name_en": c.name_en,
                    "definition": c.definition, "synonyms": c.synonyms,
                    "broader_id": c.broader_id, "status": c.status, "version": c.version})
    out.sort(key=lambda x: x["name_fa"])
    return {"total": len(out), "version": S.VOCAB_VERSION, "concepts": out[:60]}


# ------------------------------------------------ پیشنهادهای توجیه‌دار
class SupervisorQuery(BaseModel):
    topic_text: str = Field(..., min_length=3, max_length=600)
    field: str = Field("", max_length=120)
    skills: list[str] = Field(default_factory=list)


@router.post("/recommendations/supervisors", summary="پیشنهاد استاد راهنما با شروط رسمی، دلیل و نسخهٔ الگوریتم")
def supervisors(body: SupervisorQuery, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return S.recommend_supervisors(db, body.topic_text, field=body.field, skills=body.skills)


@router.get("/recommendations/collaborations", summary="نامزدهای همکاری استنتاجی برای کاربر فعلی (با سلب صراحت)")
def collaborations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return S.collaboration_candidates(db, user)


# ------------------------------------------------ عملیات مدیریتی (متولی داده / مدیر فنی)
@router.post("/integration-runs", summary="اجرای ورود داده از منبع (idempotent، نسخه‌دار)")
def start_integration(user: User = Depends(require_roles("research_manager", "system_admin")),
                      db: Session = Depends(get_db)):
    stats = S.run_integration(db)
    db.commit()
    return stats


@router.get("/integration-runs", summary="وضعیت اجراهای ورود داده و عقب‌ماندگی همگام‌سازی")
def list_integration_runs(user: User = Depends(require_roles("research_manager", "system_admin")),
                          db: Session = Depends(get_db)):
    from ..models import IntegrationRun as IR
    runs = db.query(IR).order_by(IR.created_at.desc()).limit(10).all()
    return [{"id": r.id, "source_system": r.source_system, "status": r.status,
             "created_at": str(r.created_at), "stats": r.stats} for r in runs]


@router.post("/inference-runs", summary="اجرای قاعدهٔ استنتاج (R1/R2) — ابطال و بازمحاسبهٔ کامل")
def start_inference(rule: str, user: User = Depends(require_roles("research_manager", "system_admin")),
                    db: Session = Depends(get_db)):
    try:
        out = S.run_inference(db, rule, user)
        db.commit()
        return out
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/inference-runs", summary="تاریخچهٔ اجرای قواعد استنتاج")
def list_inference_runs(user: User = Depends(require_roles("research_manager", "system_admin")),
                        db: Session = Depends(get_db)):
    from ..models import InferenceRun as IRR
    runs = db.query(IRR).order_by(IRR.created_at.desc()).limit(10).all()
    return [{"id": r.id, "rule": r.rule_code, "version": r.rule_version, "status": r.status,
             "created_at": str(r.created_at), "stats": r.stats} for r in runs]


@router.get("/resolution-cases", summary="پرونده‌های تطبیق موجودیت (متولی داده)")
def list_cases(status: str = "", user: User = Depends(require_roles("research_manager", "system_admin")),
               db: Session = Depends(get_db)):
    from ..models import ResolutionCase as RC
    q = db.query(RC)
    if status:
        q = q.filter(RC.decision == status)
    cases = q.order_by(RC.score.desc()).limit(30).all()
    S.rebuild_projection(db)
    out = []
    for c in cases:
        a = S._projection["ent"].get(c.entity_a_id, {})
        b = S._projection["ent"].get(c.entity_b_id, {})
        out.append({"id": c.id, "score": c.score, "decision": c.decision,
                    "evidence": c.evidence, "reason": c.reason,
                    "entity_a": {"id": a.get("id"), "name": a.get("name"), "ref": a.get("ref_id")},
                    "entity_b": {"id": b.get("id"), "name": b.get("name"), "ref": b.get("ref_id")},
                    "created_at": str(c.created_at)})
    return out


class ResolutionDecision(BaseModel):
    decision: str = Field(..., pattern="^(merge|separate)$")
    reason: str = Field("", max_length=400)


@router.post("/resolution-cases/{case_id}/decisions", summary="تصمیم تطبیق: ادغام یا تفکیک (قابل بازگشت)")
def decide(case_id: int, body: ResolutionDecision,
           user: User = Depends(require_roles("research_manager", "system_admin")),
           db: Session = Depends(get_db)):
    try:
        out = S.decide_case(db, case_id, body.decision, user, body.reason)
        db.commit()
        return out
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/admin/quality", summary="عکس فوری کیفیت داده معنایی (متولی داده / مدیر فنی)")
def quality(user: User = Depends(require_roles("research_manager", "system_admin")),
            db: Session = Depends(get_db)):
    return S.quality_snapshot(db)


@router.post("/projection/rebuild", summary="بازسازی کامل نمای گراف از دفتر ثبت (اثبات بازتولیدپذیری)")
def rebuild(user: User = Depends(require_roles("research_manager", "system_admin")),
            db: Session = Depends(get_db)):
    ver = S.rebuild_projection(db, force=True)
    return {"projection_version": ver, "rebuilt": True,
            "note": "نمای گرافی همیشه از دفتر ثبت بازسازی می‌شود؛ خودش مرجع نیست."}
