"""لایه معنایی و گراف دانش پژوهشیار۳۶۰ — بافته‌شده در تار و پود سامانه.

اقتباس سند «گراف دانش و لایه معنایی دانشگاه» برای این استقرار:
- دفتر ثبت معتبر: جداول semantic_* در پایگاه‌دادهٔ خود سامانه (نقش PostgreSQL سند)
- نمای گرافی: adjacency درون‌حافظه‌ای «فقط قابل بازسازی از دفتر ثبت» (نقش Neo4j سند)
  با شمارهٔ نسخه؛ هیچ نوشتن معنایی مستقیم روی نما انجام نمی‌شود.
- جست‌وجوی ترکیبی: تطابق دقیق شناسه + واژگانی + مفهومی (جایگزین آفلاین pgvector)
- استنتاج محدود و نسخه‌دار بدون بازخورد چرخه‌ای؛ تطبیق موجودیت با شواهد قوی/کمکی
- سیاست دسترسی روی رابطه و مسیر (نه فقط گره) — بخش ۱۵.۱ سند

قاعدهٔ طلایی سند: رابطه‌ای که الگوریتم پیشنهاد می‌کند هرگز «همکاری واقعی» یا
«تخصص تأییدشده» ثبت نمی‌شود؛ روابط استنتاجی origin=inferred و review=pending دارند.
"""
from __future__ import annotations

import uuid
from collections import deque

from sqlalchemy.orm import Session

from ..core.config import APP_VERSION
from ..core.semantic_norm import TfidfIndex, jaccard, name_similarity, normalize_text, tokenize
from ..core.utils import now_utc
from ..models import (
    EntityIdentifier, EventLog, InferenceRun, IntegrationRun, MergeOperation,
    RelationAssertion, ResolutionCase, ResearchProfile, ResearchRequest, SemanticConcept,
    SemanticEntity, SourceRecord, User,
)

SOURCE_CORE = "pazhoheshyar-core"
VOCAB_VERSION = "voc-1.0.0"
RECOMMEND_VERSION = "sup-1.0.0"
EVIDENCE_VERSION = "ev-1.0.0"
INFERENCE_VERSIONS = {
    "R1": "inf-r1-1.0.0",   # شواهد پژوهشِ موضوعی از مقالات (محدود، قابل ابطال)
    "R2": "inf-r2-1.0.0",   # نامزد همکاری از اشتراک مفاهیم/مهارت‌های رسمی
}

# ------------------------------------------- واژگان روابط + قید نوع مبدأ/مقصد (بخش ۱۲ سند)
PREDICATES = {
    "AFFILIATED_WITH":        ("وابستگی سازمانی", ("Person",), ("Organization",)),
    "MEMBER_OF":              ("عضویت در واحد", ("Person",), ("AcademicUnit",)),
    "HAS_SKILL":              ("دارای مهارت", ("Person",), ("Skill",)),
    "INTERESTED_IN":          ("علاقه‌مندی", ("Person",), ("Concept",)),
    "EXPERT_IN":              ("تخصص", ("Person",), ("Concept",)),
    "AUTHORED":               ("نویسندگی", ("Person",), ("Publication",)),
    "ABOUT_FIELD":            ("حوزهٔ موضوعی", ("Topic", "ResearchRequest", "ResearchProject", "Publication"), ("Concept",)),
    "REQUIRES_SKILL":         ("نیازمند مهارت", ("Topic", "ResearchRequest"), ("Skill",)),
    "PROPOSED_BY":            ("پیشنهاددهنده", ("ResearchRequest",), ("Person",)),
    "OFFERED_SUPPORT":        ("اعلام آمادگی", ("Person",), ("ResearchRequest",)),
    "LEADS":                  ("راهبری پروژه", ("Person",), ("ResearchProject",)),
    "PARTICIPATES_IN":        ("مشارکت در پروژه", ("Person",), ("ResearchProject",)),
    "DERIVED_FROM":           ("مشتق از درخواست", ("ResearchProject",), ("ResearchRequest",)),
    "RESEARCHED_ON":          ("شواهد پژوهش موضوعی", ("Person",), ("Concept",)),          # استنتاجی R1
    "CANDIDATE_COLLABORATOR": ("نامزد همکاری", ("Person",), ("Person",)),                 # استنتاجی R2
}
INFERRED_PREDICATES = {"RESEARCHED_ON", "CANDIDATE_COLLABORATOR"}
KIND_LABELS = {
    "Person": "شخص", "Organization": "سازمان", "AcademicUnit": "واحد دانشگاهی",
    "Skill": "مهارت", "Concept": "مفهوم علمی", "Topic": "موضوع پژوهشی",
    "ResearchRequest": "درخواست پژوهش", "ResearchProject": "پروژه پژوهشی", "Publication": "اثر علمی",
}
ORIGIN_LABELS = {"asserted": "رسمی", "extracted": "استخراج‌شده", "inferred": "استنتاجی"}


def _uuid() -> str:
    return str(uuid.uuid4())


# ============================================================ دفتر ثبت موجودیت‌ها
def get_or_create_entity(db: Session, kind: str, display_name: str, ref_table: str = "",
                         ref_id: str = "", summary: str = "", meta: dict | None = None) -> SemanticEntity:
    """ایجاد/یافتن موجودیت — بدون ref، یکتایی با (kind، نام نرمال‌شده)."""
    disp = display_name.strip()[:300]
    norm = normalize_text(disp)[:300]
    if ref_table and ref_id:
        ent = db.query(SemanticEntity).filter(
            SemanticEntity.kind == kind, SemanticEntity.ref_table == ref_table,
            SemanticEntity.ref_id == str(ref_id)).one_or_none()
    else:
        ent = db.query(SemanticEntity).filter(
            SemanticEntity.kind == kind, SemanticEntity.display_name_norm == norm).one_or_none()
    if ent:
        if summary and not ent.summary:
            ent.summary = summary
        return ent
    ent = SemanticEntity(id=_uuid(), kind=kind, ref_table=ref_table, ref_id=str(ref_id or ""),
                         display_name=disp, display_name_norm=norm, summary=summary or "",
                         meta=meta or {}, status="active")
    db.add(ent)
    db.flush()
    return ent


def resolve_entity(db: Session, eid: str) -> SemanticEntity | None:
    """پیگیری زنجیرهٔ ادغام تا موجودیت کانونی (ادغام قابل بازگشت)."""
    seen = set()
    ent = db.get(SemanticEntity, eid)
    while ent and ent.status == "merged" and ent.merged_into and ent.id not in seen:
        seen.add(ent.id)
        ent = db.get(SemanticEntity, ent.merged_into)
    return ent


def add_identifier(db: Session, ent: SemanticEntity, scheme: str, value: str,
                   source_system: str = SOURCE_CORE, confidence: float = 1.0) -> EntityIdentifier:
    v = str(value).strip()[:400]
    row = db.query(EntityIdentifier).filter(
        EntityIdentifier.entity_id == ent.id, EntityIdentifier.scheme == scheme,
        EntityIdentifier.value == v).one_or_none()
    if row:
        return row
    row = EntityIdentifier(entity_id=ent.id, scheme=scheme, value=v,
                           source_system=source_system, confidence=confidence)
    db.add(row)
    db.flush()
    return row


def get_or_create_concept(db: Session, name_fa: str, name_en: str = "", definition: str = "",
                          synonyms: list | None = None, broader_id: str | None = None,
                          status: str = "approved") -> SemanticConcept:
    """واژهٔ کنترل‌شده — «یادگیری ماشین» و «ML» نام‌های یک مفهوم‌اند، نه دو مفهوم."""
    norm = normalize_text(name_fa)
    c = None
    for row in db.query(SemanticConcept).all():  # حجم واژگان سامانه محدود است
        if normalize_text(row.name_fa) == norm:
            c = row
            break
        if name_en and row.name_en and normalize_text(row.name_en) == normalize_text(name_en):
            c = row
            break
        for syn in row.synonyms or []:
            if normalize_text(syn) == norm:
                c = row
                break
        if c:
            break
    if c:
        if name_en and not c.name_en:
            c.name_en = name_en
        return c
    c = SemanticConcept(id=_uuid(), name_fa=name_fa.strip()[:200], name_en=name_en.strip()[:200],
                        definition=definition, synonyms=synonyms or [], broader_id=broader_id,
                        status=status, version=VOCAB_VERSION)
    db.add(c)
    db.flush()
    return c


def concept_entity(db: Session, c: SemanticConcept, kind: str = "Concept") -> SemanticEntity:
    """مفهوم/مهارت واژگانی → موجودیت گراف (خانوادهٔ Concept یا Skill)."""
    ent = db.query(SemanticEntity).filter(
        SemanticEntity.kind == kind, SemanticEntity.ref_table == "semantic_concepts",
        SemanticEntity.ref_id == c.id).one_or_none()
    if not ent:
        ent = get_or_create_entity(db, kind, c.name_fa, ref_table="semantic_concepts", ref_id=c.id,
                                   summary=c.definition,
                                   meta={"synonyms": c.synonyms or [], "name_en": c.name_en})
    return ent


def concept_for_name(db: Session, name: str) -> SemanticConcept:
    return get_or_create_concept(db, name.strip())


# ============================================================ ثبت ادعاها با قید نوع
def assert_relation(db: Session, subject: SemanticEntity, predicate: str, obj: SemanticEntity,
                    origin: str = "asserted", confidence: float | None = 1.0,
                    source_system: str = SOURCE_CORE, source_record_id: str | None = None,
                    evidence_ref: list | None = None, access_policy: str = "public",
                    review_status: str = "approved", payload: dict | None = None,
                    rule_version: str = "", valid_from=None) -> tuple[RelationAssertion, bool]:
    """ثبت ادعای رابطه با اعتبارسنجی نوع مبدأ/مقصد و یکتایی (بخش ۳.۳ و ۱۲ سند)."""
    if predicate not in PREDICATES:
        raise ValueError(f"رابطهٔ ناشناخته: {predicate}")
    _label, sub_kinds, obj_kinds = PREDICATES[predicate]
    if subject.kind not in sub_kinds or obj.kind not in obj_kinds:
        raise ValueError(f"نوع مبدأ/مقصد نامعتبر برای {predicate}: "
                         f"{subject.kind}→{obj.kind}")
    if origin == "inferred" and predicate not in INFERRED_PREDICATES:
        raise ValueError(f"رابطهٔ استنتاجی مجاز نیست: {predicate}")

    q = db.query(RelationAssertion).filter(
        RelationAssertion.subject_entity_id == subject.id,
        RelationAssertion.predicate_code == predicate,
        RelationAssertion.object_entity_id == obj.id,
        RelationAssertion.origin == origin,
        RelationAssertion.source_system == source_system)
    if origin == "inferred":
        q = q.filter(RelationAssertion.rule_or_model_version == rule_version)
    row = q.one_or_none()
    if row:
        return row, False
    row = RelationAssertion(
        id=_uuid(), subject_entity_id=subject.id, predicate_code=predicate,
        object_entity_id=obj.id, origin=origin, source_system=source_system,
        source_record_id=source_record_id, evidence_ref=evidence_ref or [],
        confidence=confidence, valid_from=valid_from or now_utc(), observed_at=now_utc(),
        access_policy=access_policy, rule_or_model_version=rule_version,
        review_status=review_status, payload=payload or {})
    db.add(row)
    db.flush()
    return row, True


# ============================================================ نمای گراف قابل بازسازی
_projection: dict = {"version": "", "built_at": None, "adj": {}, "ent": {}, "tfidf": None,
                     "ident": {}}


def projection_version(db: Session) -> str:
    """نسخهٔ نما = تابع دفتر ثبت — تغییر ادعا/موجودیت (حتی ادغام) نما را کهنه می‌کند."""
    n_ent = db.query(SemanticEntity).count()
    n_act = db.query(SemanticEntity).filter(SemanticEntity.status == "active").count()
    n_cl = db.query(RelationAssertion).count()
    mx = db.query(RelationAssertion.id).order_by(RelationAssertion.created_at.desc()).first()
    seed = f"{n_ent}:{n_act}:{n_cl}:{mx[0] if mx else '-'}"
    import hashlib
    return "pv-" + hashlib.sha1(seed.encode()).hexdigest()[:12]


def rebuild_projection(db: Session, force: bool = False) -> str:
    """بازسازی کامل نما از دفتر ثبت — اثبات پذیرش «گراف از دفتر ثبت قابل بازسازی است»."""
    ver = projection_version(db)
    if _projection["version"] == ver and not force:
        return ver
    adj: dict[str, list] = {}
    ent_map: dict[str, dict] = {}
    ident: dict[str, set[str]] = {}
    for ent in db.query(SemanticEntity).filter(SemanticEntity.status == "active").all():
        ent_map[ent.id] = {"id": ent.id, "kind": ent.kind, "name": ent.display_name,
                           "summary": ent.summary or "", "ref_table": ent.ref_table,
                           "ref_id": ent.ref_id, "meta": ent.meta or {},
                           "updated_at": str(ent.updated_at or "")}
    for row in db.query(EntityIdentifier).all():
        ident.setdefault(row.entity_id, set()).add(f"{row.scheme}:{row.value.lower()}")
    for cl in db.query(RelationAssertion).all():
        a, b = cl.subject_entity_id, cl.object_entity_id
        edge = {"claim_id": cl.id, "pred": cl.predicate_code, "origin": cl.origin,
                "policy": cl.access_policy, "conf": cl.confidence,
                "review": cl.review_status, "version": cl.rule_or_model_version or "",
                "valid_to": str(cl.valid_to or ""),
                "evidence": cl.evidence_ref or [], "payload": cl.payload or {}}
        adj.setdefault(a, []).append({**edge, "other": b, "dir": "out"})
        adj.setdefault(b, []).append({**edge, "other": a, "dir": "in"})
    idx = TfidfIndex()
    # غنی‌سازی برداری از طریق گراف: نام همسایه‌های مفهومی/مهارتیِ روابط عمومی
    # به متن هر موجودیت اضافه می‌شود (جست‌وجوی مفهومی سند، بخش ۱ — نه فقط شباهت کلمه)
    link_preds = {"EXPERT_IN", "INTERESTED_IN", "HAS_SKILL", "ABOUT_FIELD",
                  "REQUIRES_SKILL", "RESEARCHED_ON", "MEMBER_OF"}
    nbr: dict[str, list[str]] = {}
    for eid, edges in adj.items():
        for e in edges:
            if e["pred"] in link_preds and e["policy"] in ("public", "internal"):
                nm = ent_map.get(e["other"], {}).get("name")
                if nm:
                    nbr.setdefault(eid, []).append(nm)
    for eid, e in ent_map.items():
        text = e["name"] + " " + e["summary"]
        idents = " ".join(sorted(ident.get(eid, set())))
        idx.add(eid, text + " " + idents + " " + " ".join(sorted(set(nbr.get(eid, [])))))
    _projection.update(version=ver, built_at=now_utc(), adj=adj, ent=ent_map,
                       tfidf=idx, ident=ident)
    return ver


# ============================================================ سیاست دسترسی (بخش ۲ و ۱۵.۱ سند)
MANAGER_ROLES = {"research_manager", "system_admin"}
SENSITIVE_PREDICATES = {"AUTHORED"}          # مشتق از فیلد حساس پروفایل
RESTRICTED_INFERRED = {"RESEARCHED_ON"}      # ترکیب داده حساس → خروجی هم حساس


def can_view_claim(user: User | None, claim_like: dict) -> bool:
    """سیاست روی رابطه: public همهٔ لاگین‌ها؛ internal همه؛ restricted فقط مدیر یا خود شخص."""
    pol = claim_like.get("policy", "public")
    if pol == "public":
        return True
    if user is None:
        return False
    if set(user.roles or []) & MANAGER_ROLES:
        return True
    if pol in ("internal",):
        return True
    # restricted — فقط مدیر یا مالکِ شخصِ طرف رابطه
    try:
        person_eid = claim_like.get("owner_entity_id") or claim_like.get("other")
        ent = _projection["ent"].get(person_eid, {})
        if ent.get("kind") == "Person" and ent.get("ref_table") == "users" \
                and str(ent.get("ref_id")) == str(user.id):
            return True
    except Exception:
        pass
    return False


def _edge_owner(e: dict) -> dict:
    """برای ارزیابی restricted: مالکِ رابطه شخصِ طرفِ انسان است."""
    return {**e, "owner_entity_id": e.get("other") if e.get("dir") == "out" else e.get("claim_subject")}


def visible_adj(user: User | None, eid: str) -> list[dict]:
    adj = _projection["adj"].get(eid, [])
    out = []
    for e in adj:
        ee = {**e, "owner_entity_id": eid}   # مالک = مرکز (شخصِ نگاه‌شده)
        if can_view_claim(user, ee):
            out.append(e)
    return out


# ============================================================ پرس‌وجوهای گراف
def neighborhood(db: Session, user: User | None, eid: str, depth: int = 1, limit: int = 40) -> dict:
    """همسایگی محدود — عمق ≤۲ و سقف گره؛ مسیرِ رسیدن هر گره گزارش می‌شود."""
    rebuild_projection(db)
    ent = resolve_entity(db, eid)
    if not ent or ent.id not in _projection["ent"]:
        return {"center": None, "nodes": [], "edges": []}
    depth = max(1, min(int(depth), 2))
    limit = max(1, min(int(limit), 60))
    center = ent.id
    seen: dict[str, dict] = {center: {"hops": 0, "via": []}}
    edges_out: list[dict] = []
    qd = deque([center])
    while qd and len(seen) < limit + 1:
        cur = qd.popleft()
        if seen[cur]["hops"] >= depth:
            continue
        for e in visible_adj(user, cur):
            other = e["other"]
            if other not in _projection["ent"]:
                continue
            edges_out.append({"subject": cur, "object": other, "pred": e["pred"],
                              "origin": e["origin"], "policy": e["policy"],
                              "claim_id": e["claim_id"], "conf": e["conf"]})
            if other not in seen:
                seen[other] = {"hops": seen[cur]["hops"] + 1,
                               "via": [{"from": cur, "pred": e["pred"], "dir": e["dir"],
                                        "origin": e["origin"]}]}
                qd.append(other)
                if len(seen) >= limit + 1:
                    break
    nodes = []
    for eid2, meta in seen.items():
        e = _projection["ent"][eid2]
        nodes.append({"id": eid2, "kind": e["kind"], "name": e["name"], "kind_fa": KIND_LABELS.get(e["kind"], e["kind"]),
                      "hops": meta["hops"], "via": meta["via"]})
    nodes.sort(key=lambda n: (n["hops"], n["name"]))
    edges_out = edges_out[: limit * 3]
    return {"center": {"id": center, "kind": ent.kind, "name": ent.display_name,
                       "kind_fa": KIND_LABELS.get(ent.kind, ent.kind)},
            "nodes": nodes, "edges": edges_out}


def find_paths(db: Session, user: User | None, src_eid: str, dst_eid: str,
               max_hops: int = 4, limit: int = 5) -> dict:
    """مسیرهای مجاز بین دو موجودیت — با فیلتر سیاست روی هر گام (بخش ۱۵.۱ سند)."""
    rebuild_projection(db)
    a, b = resolve_entity(db, src_eid), resolve_entity(db, dst_eid)
    if not a or not b or a.id not in _projection["ent"] or b.id not in _projection["ent"]:
        return {"paths": []}
    max_hops = max(1, min(int(max_hops), 4))
    paths: list[dict] = []
    parent: dict[str, tuple[str, dict]] = {a.id: (None, {})}
    qd = deque([a.id])
    while qd and len(paths) < limit:
        cur = qd.popleft()
        hops_cur = 0
        p0 = parent[cur]
        while p0[0] is not None:
            hops_cur += 1
            p0 = parent[p0[0]]
        if cur == b.id and hops_cur > 0:
            chain, node = [], cur
            while parent[node][0] is not None:
                chain.append(parent[node][1])
                node = parent[node][0]
            chain.reverse()
            steps = [{"pred": e["pred"], "pred_fa": PREDICATES[e["pred"]][0],
                      "origin": e["origin"], "dir": e["dir"],
                      "node": {"id": e["other"], "kind": _projection["ent"][e["other"]]["kind"],
                               "name": _projection["ent"][e["other"]]["name"],
                               "kind_fa": KIND_LABELS.get(_projection["ent"][e["other"]]["kind"], "")}}
                     for e in chain]
            paths.append({"hops": len(chain), "steps": steps})
            continue
        if hops_cur >= max_hops:
            continue
        for e in visible_adj(user, cur):
            nxt = e["other"]
            if nxt in parent:
                continue
            parent[nxt] = (cur, e)
            if len(parent) > 400:   # سقف پیمایش — جلوگیری از بارگذاری کل گراف در مرورگر
                qd.clear()
                break
            qd.append(nxt)
    return {"paths": paths}


def graph_overview(db: Session, user: User | None) -> dict:
    """نمای کلی شبکه برای صفحهٔ دانش — شمارش‌ها فقط از روابط مجاز کاربر می‌آید."""
    rebuild_projection(db)
    kinds: dict[str, int] = {}
    for e in _projection["ent"].values():
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    pred_count: dict[str, dict] = {}
    visible_claims = 0
    for eid in _projection["ent"]:
        for e in visible_adj(user, eid):
            if e["dir"] != "out":
                continue
            visible_claims += 1
            pc = pred_count.setdefault(e["pred"], {"fa": PREDICATES[e["pred"]][0],
                                                   "asserted": 0, "extracted": 0, "inferred": 0})
            pc[e["origin"]] = pc.get(e["origin"], 0) + 1
    return {"version": _projection["version"], "built_at": str(_projection["built_at"]),
            "kinds": kinds, "kind_labels": KIND_LABELS,
            "predicates": [{"code": k, **v} for k, v in sorted(pred_count.items())],
            "visible_claims": visible_claims}


# ============================================================ ورود داده و یکپارچه‌سازی (بخش ۵ سند)
def run_integration(db: Session, source_system: str = SOURCE_CORE) -> dict:
    """خط پردازش سند ۵.۱ روی دادهٔ موجود خود سامانه — idempotent و نسخه‌دار.

    دریافت → ثبت منشأ → اعتبارسنجی (قید نوع) → نگاشت معنایی → ثبت ادعای معتبر.
    دادهٔ حساس کپی نمی‌شود؛ فقط روابط و حداقل ویژگی مجاز.
    """
    from ..models import Offer, Project, ProjectMember, Topic as TopicModel

    stats = {"entities": {}, "claims": {}, "publications": 0}
    run_id = _uuid()

    def bump(kind, n=1):
        stats["entities"][kind] = stats["entities"].get(kind, 0) + n

    def bumpc(pred, n=1):
        stats["claims"][pred] = stats["claims"].get(pred, 0) + n

    src = SourceRecord(id=_uuid(), source_system=source_system, record_type="core-snapshot",
                       external_id=run_id, raw={"integration_run": run_id})
    db.add(src)
    db.flush()

    org = get_or_create_entity(db, "Organization", "دانشگاه نمونهٔ استقرار", ref_table="orgs", ref_id="main",
                               summary="سازمان مادر استقرار فعلی سامانه")

    persons: dict[int, SemanticEntity] = {}
    for u in db.query(User).all():
        p = get_or_create_entity(db, "Person", u.display_name, ref_table="users", ref_id=str(u.id),
                                 summary="، ".join(u.roles or []))
        add_identifier(db, p, "portal_uid", u.username, source_system)
        if u.sso_sub:
            add_identifier(db, p, "sso_sub", f"{u.sso_issuer}#{u.sso_sub}", source_system, 1.0)
        _, created = assert_relation(db, p, "AFFILIATED_WITH", org, source_system=source_system,
                                     source_record_id=src.id,
                                     payload={"roles": u.roles or [], "valid_from": str(u.created_at or "")})
        if created:
            bumpc("AFFILIATED_WITH")
        persons[u.id] = p
        bump("Person")

    for prof in db.query(ResearchProfile).all():
        p = persons.get(prof.user_id)
        if not p:
            continue
        if (prof.faculty_name or "").strip():
            unit = get_or_create_entity(db, "AcademicUnit", prof.faculty_name.strip(),
                                        ref_table="academic_units", ref_id=normalize_text(prof.faculty_name)[:60])
            bump("AcademicUnit")
            _, cr = assert_relation(db, p, "MEMBER_OF", unit, source_system=source_system,
                                    source_record_id=src.id, valid_from=prof.updated_at)
            if cr:
                bumpc("MEMBER_OF")
        for s in prof.skills or []:
            skill = concept_entity(db, get_or_create_concept(db, s), kind="Skill")
            bump("Skill")
            _, cr = assert_relation(db, p, "HAS_SKILL", skill, source_system=source_system, source_record_id=src.id)
            if cr:
                bumpc("HAS_SKILL")
        for it in prof.interests or []:
            ce = concept_entity(db, get_or_create_concept(db, it))
            bump("Concept")
            _, cr = assert_relation(db, p, "INTERESTED_IN", ce, source_system=source_system, source_record_id=src.id)
            if cr:
                bumpc("INTERESTED_IN")
        for ex in prof.expertise or []:
            ce = concept_entity(db, get_or_create_concept(db, ex))
            bump("Concept")
            _, cr = assert_relation(db, p, "EXPERT_IN", ce, source_system=source_system, source_record_id=src.id)
            if cr:
                bumpc("EXPERT_IN")
        if (prof.field_of_study or "").strip():
            fe = concept_entity(db, get_or_create_concept(db, prof.field_of_study.strip()))
            bump("Concept")
            _, cr = assert_relation(db, p, "INTERESTED_IN", fe, source_system=source_system, source_record_id=src.id)
            if cr:
                bumpc("INTERESTED_IN")
        # مقالات — فیلد حساس پروفایل: فقط رابطه ثبت می‌شود، محتوا کپی نمی‌شود
        pubs = prof.publications or []
        for i, pub in enumerate(pubs):
            title = pub.get("title") if isinstance(pub, dict) else str(pub)
            year = pub.get("year") if isinstance(pub, dict) else ""
            if not (title or "").strip():
                continue
            pe = get_or_create_entity(db, "Publication", title.strip()[:300],
                                      ref_table="profile_publications", ref_id=f"{prof.user_id}:{i}",
                                      meta={"year": year})
            bump("Publication")
            stats["publications"] += 1
            _, cr = assert_relation(db, p, "AUTHORED", pe, origin="extracted", confidence=0.6,
                                    source_system=source_system, source_record_id=src.id,
                                    access_policy="restricted", review_status="pending",
                                    payload={"author_index": i})
            if cr:
                bumpc("AUTHORED")
            if (prof.field_of_study or "").strip():
                fe = concept_entity(db, get_or_create_concept(db, prof.field_of_study.strip()))
                _, cr = assert_relation(db, pe, "ABOUT_FIELD", fe, origin="extracted", confidence=0.5,
                                        source_system=source_system, source_record_id=src.id,
                                        access_policy="restricted", review_status="pending")
                if cr:
                    bumpc("ABOUT_FIELD")

    requests_entities: dict[int, SemanticEntity] = {}
    for r in db.query(ResearchRequest).filter(ResearchRequest.status != "draft").all():
        re_ = get_or_create_entity(db, "ResearchRequest", r.title[:300], ref_table="research_requests",
                                   ref_id=str(r.id), summary=(r.summary or "")[:400],
                                   meta={"status": r.status})
        bump("ResearchRequest")
        requests_entities[r.id] = re_
        stu = persons.get(r.student_id)
        if stu:
            _, cr = assert_relation(db, re_, "PROPOSED_BY", stu, source_system=source_system,
                                    source_record_id=src.id)
            if cr:
                bumpc("PROPOSED_BY")
        if (r.field or "").strip():
            fe = concept_entity(db, get_or_create_concept(db, r.field.strip()))
            bump("Concept")
            _, cr = assert_relation(db, re_, "ABOUT_FIELD", fe, source_system=source_system, source_record_id=src.id)
            if cr:
                bumpc("ABOUT_FIELD")
        for s in r.skills or []:
            skill = concept_entity(db, get_or_create_concept(db, s), kind="Skill")
            bump("Skill")
            _, cr = assert_relation(db, re_, "REQUIRES_SKILL", skill, source_system=source_system, source_record_id=src.id)
            if cr:
                bumpc("REQUIRES_SKILL")

    for t in db.query(TopicModel).filter(TopicModel.is_active).all():
        te = get_or_create_entity(db, "Topic", t.title[:300], ref_table="topics", ref_id=str(t.id),
                                  summary=(t.problem_statement or "")[:400])
        bump("Topic")
        if (t.field or "").strip():
            fe = concept_entity(db, get_or_create_concept(db, t.field.strip()))
            _, cr = assert_relation(db, te, "ABOUT_FIELD", fe, source_system=source_system, source_record_id=src.id)
            if cr:
                bumpc("ABOUT_FIELD")
        for s in t.required_skills or []:
            skill = concept_entity(db, get_or_create_concept(db, s), kind="Skill")
            _, cr = assert_relation(db, te, "REQUIRES_SKILL", skill, source_system=source_system, source_record_id=src.id)
            if cr:
                bumpc("REQUIRES_SKILL")

    for o in db.query(Offer).filter(Offer.status.in_(["sent", "viewed", "in_dialogue", "accepted", "converted_to_project"])).all():
        p = persons.get(o.professor_id)
        re_ = requests_entities.get(o.request_id)
        if p and re_:
            _, cr = assert_relation(db, p, "OFFERED_SUPPORT", re_, source_system=source_system,
                                    source_record_id=src.id, payload={"offer_id": o.id})
            if cr:
                bumpc("OFFERED_SUPPORT")

    from ..models import Project as ProjectModel
    for pr in db.query(ProjectModel).all():
        pe = get_or_create_entity(db, "ResearchProject", pr.title[:300], ref_table="projects",
                                  ref_id=str(pr.id), meta={"status": pr.status})
        bump("ResearchProject")
        re_ = requests_entities.get(pr.request_id)
        if re_:
            _, cr = assert_relation(db, pe, "DERIVED_FROM", re_, source_system=source_system, source_record_id=src.id)
            if cr:
                bumpc("DERIVED_FROM")
        lead = persons.get(pr.lead_professor_id)
        if lead:
            _, cr = assert_relation(db, lead, "LEADS", pe, source_system=source_system, source_record_id=src.id)
            if cr:
                bumpc("LEADS")
        for m in db.query(ProjectMember).filter(ProjectMember.project_id == pr.id).all():
            p = persons.get(m.user_id)
            if p:
                _, cr = assert_relation(db, p, "PARTICIPATES_IN", pe, source_system=source_system,
                                        source_record_id=src.id, payload={"role": m.role})
                if cr:
                    bumpc("PARTICIPATES_IN")

    run = IntegrationRun(id=run_id, source_system=source_system, status="completed", stats=stats)
    db.add(run)
    db.add(EventLog(type="semantic_outbox", payload={
        "event": "integration_completed", "run_id": run_id, "source_system": source_system,
        "stats": stats, "version": APP_VERSION}))
    db.flush()
    return {"run_id": run_id, "stats": stats}


# ============================================================ جست‌وجوی ترکیبی (بخش ۱۰ سند)
_INTENT_KINDS = [
    (("استاد", "استادان", "اساتید", "استادان راهنما", "راهنما", "professor"), ("Person",), "professor"),
    (("دانشجو", "دانشجویان", "student"), ("Person",), "student"),
    (("مقاله", "مقالات", "publication", "paper", "اثر"), ("Publication",), None),
    (("پروژه", "پروژه‌ها", "project"), ("ResearchProject",), None),
    (("درخواست", "درخواست‌ها", "استخر"), ("ResearchRequest",), None),
    (("موضوع", "موضوعات", "topic", "بانک موضوعات"), ("Topic",), None),
    (("مهارت", "مهارت‌ها", "skill"), ("Skill",), None),
    (("مفهوم", "مفاهیم", "حوزه", "concept"), ("Concept",), None),
    (("دانشکده", "گروه", "واحد", "faculty"), ("AcademicUnit",), None),
]


def parse_intent(q: str) -> dict:
    """تحلیل قصد — تعیین‌شده و بدون LLM (الزام امنیتی ۱۰.۳: مدل هرگز پرس‌وجو تولید نمی‌کند)."""
    n = normalize_text(q)
    kinds: set[str] = set()
    role = None
    for keys, ks, rl in _INTENT_KINDS:
        if any(k in n for k in keys):
            kinds.update(ks)
            if rl:
                role = rl
    import re as _re
    faculty = None
    m = _re.search(r"دانشکده[‌\s]+([\w‌\s]{2,40})", q)
    if m:
        faculty = normalize_text(m.group(1))
    return {"kinds": kinds or None, "role": role, "faculty": faculty}


def semantic_search(db: Session, user: User | None, q: str, types: str = "", limit: int = 20) -> dict:
    """جست‌وجوی ترکیبی: دقیق شناسه > دقیق نام > واژگانی/برداری > مفهوم؛ همه آگاه از مجوز."""
    rebuild_projection(db)
    q = (q or "").strip()[:200]
    if not q:
        return {"query": q, "results": []}
    limit = max(1, min(int(limit), 40))
    intent = parse_intent(q)
    if types:
        intent["kinds"] = {t.strip() for t in types.split(",") if t.strip()} or intent["kinds"]
    nq = normalize_text(q)
    scores: dict[str, dict] = {}

    def add(eid, score, reason):
        cur = scores.setdefault(eid, {"score": 0.0, "reasons": []})
        cur["score"] += score
        if reason not in cur["reasons"][:3]:
            cur["reasons"].append(reason)

    # ۱) تطابق دقیق شناسه — اولویت بالای تضمین‌شده (نباید زیر شباهت برداری برود)
    for eid, idents in _projection["ident"].items():
        if f"portal_uid:{nq}" in idents or any(i.endswith(":" + nq) for i in idents):
            add(eid, 100.0, "تطابق دقیق شناسه")
    # ۲) تطابق دقیق نام
    for eid, e in _projection["ent"].items():
        nn = normalize_text(e["name"])
        if nn == nq:
            add(eid, 60.0, "تطابق دقیق نام")
        elif nq and nq in nn:
            add(eid, 12.0, "شامل عبارت در نام")
    # ۳) شباهت برداری سبک
    for eid, s in (_projection["tfidf"].search(q, top_k=30) or []):
        if s > 0:
            add(eid, min(s * 6.0, 18.0), "شباهت واژگانی")
    # ۴) گسترش مفهومی با مترادف‌ها
    for eid, e in _projection["ent"].items():
        syns = (e.get("meta") or {}).get("synonyms") if isinstance(e.get("meta"), dict) else []
        for syn in syns or []:
            if normalize_text(syn) == nq:
                add(eid, 30.0, "مترادف واژگان کنترل‌شده")
                break
    # فیلتر نوع/نقش + تقویت گرافی + مرتب‌سازی تعیین‌شده
    out = []
    for eid, cur in scores.items():
        e = _projection["ent"].get(eid)
        if not e:
            continue
        if intent["kinds"] and e["kind"] not in intent["kinds"]:
            continue
        if intent["role"] and e["kind"] == "Person":
            up = db.get(User, int(e["ref_id"])) if e["ref_table"] == "users" else None
            roles = up.roles if up else []
            if intent["role"] not in (roles or []):
                continue
        boost = min(len(_projection["adj"].get(eid, [])), 24) / 120.0
        out.append({"id": eid, "kind": e["kind"], "kind_fa": KIND_LABELS.get(e["kind"], e["kind"]),
                    "name": e["name"], "summary": e["summary"][:180],
                    "score": round(cur["score"] + boost, 3),
                    "reasons": cur["reasons"][:3]})
    out.sort(key=lambda x: (-x["score"], x["name"]))
    return {"query": q, "intent": {"kinds": sorted(intent["kinds"] or []), "role": intent["role"]},
            "results": out[:limit]}


# ============================================================ استنتاج محدود و نسخه‌دار (بخش ۶.۱ سند)
def run_inference(db: Session, rule_code: str, user: User | None = None) -> dict:
    """اجرای قاعدهٔ استنتاج — ورودی فقط روابط رسمی/استخراجی (بدون بازخورد چرخه‌ای)،
    خروجی همیشه inferred+pending، قابل حذف و محاسبهٔ مجدد."""
    if rule_code not in INFERENCE_VERSIONS:
        raise ValueError("قاعدهٔ ناشناخته")
    version = INFERENCE_VERSIONS[rule_code]
    rebuild_projection(db)   # نقشهٔ موجودیت‌ها برای اعتبارسنجی نوع در ثبت ادعاهای استنتاجی
    prev = db.query(RelationAssertion).filter(
        RelationAssertion.origin == "inferred",
        RelationAssertion.rule_or_model_version == version).all()
    deleted = len(prev)
    for cl in prev:
        db.delete(cl)
    db.flush()

    generated = 0
    inputs = 0
    if rule_code == "R1":
        # مقاله → موضوع (رسمی/استخراجی) و نویسندگی → شمارش موضوع برای هر شخص
        person_topics: dict[str, dict[str, list]] = {}
        about = {cl.subject_entity_id: cl.object_entity_id for cl in db.query(RelationAssertion).filter(
            RelationAssertion.predicate_code == "ABOUT_FIELD",
            RelationAssertion.origin != "inferred").all()}
        for cl in db.query(RelationAssertion).filter(
                RelationAssertion.predicate_code == "AUTHORED",
                RelationAssertion.origin != "inferred").all():
            inputs += 1
            topic_c = about.get(cl.object_entity_id)
            if not topic_c:
                continue
            person_topics.setdefault(cl.subject_entity_id, {}).setdefault(topic_c, []).append(cl.id)
        for p, tmap in person_topics.items():
            for c, claim_ids in tmap.items():
                if len(claim_ids) >= 2:   # حداقل دو اثر در یک موضوع
                    assert_relation(db, _proxy_entity(p), "RESEARCHED_ON", _proxy_entity(c),
                                    origin="inferred", confidence=0.65,
                                    source_system="inference-engine", access_policy="restricted",
                                    review_status="pending", rule_version=version,
                                    evidence_ref=[{"kind": "count", "publications": len(claim_ids)}],
                                    payload={"note": "شواهد پژوهش موضوعی است؛ تخصص تأییدشده نیست"})
                    generated += 1
    elif rule_code == "R2":
        # اشتراک ≥۲ مفهوم/مهارت رسمی → نامزد همکاری (هرگز «همکاری واقعی»)
        owner: dict[str, set[str]] = {}
        for cl in db.query(RelationAssertion).filter(
                RelationAssertion.predicate_code.in_(["INTERESTED_IN", "EXPERT_IN", "HAS_SKILL"]),
                RelationAssertion.origin == "asserted").all():
            inputs += 1
            owner.setdefault(cl.subject_entity_id, set()).add(cl.object_entity_id)
        people = [p for p, s in owner.items() if len(s) >= 2]
        obj_name = {e.id: e for e in db.query(SemanticEntity).all()}
        for i, a in enumerate(people):
            if generated >= 200:
                break
            for b in people[i + 1:]:
                shared = owner[a] & owner[b]
                if len(shared) >= 2:
                    names = [obj_name[c].display_name for c in list(shared)[:3] if c in obj_name]
                    assert_relation(db, _proxy_entity(a), "CANDIDATE_COLLABORATOR", _proxy_entity(b),
                                    origin="inferred", confidence=0.5, source_system="inference-engine",
                                    access_policy="internal", review_status="pending",
                                    rule_version=version,
                                    evidence_ref=[{"kind": "shared_concepts", "names": names}],
                                    payload={"note": "پیشنهاد الگوریتمی است؛ همکاری واقعی نیست"})
                    generated += 1

    run = InferenceRun(id=_uuid(), rule_code=rule_code, rule_version=version,
                       status="completed", created_by=user.id if user else None,
                       stats={"generated": generated, "deleted_previous": deleted, "inputs": inputs,
                              "note": "استنتاجی — با اجرای بعدی قابل ابطال و بازمحاسبه است"})
    db.add(run)
    db.flush()
    return {"run_id": run.id, "rule": rule_code, "version": version, **run.stats}


def _proxy_entity(eid: str) -> SemanticEntity:
    """هشدار: فقط برای ثبت ادعا — آبجکت سبک با همان id (بدون سفر اضافه به دیتابیس)."""
    return SemanticEntity(id=eid, kind=_projection["ent"].get(eid, {}).get("kind", "Concept"),
                          display_name=_projection["ent"].get(eid, {}).get("name", ""),
                          ref_table="", ref_id="")


# ============================================================ تطبیق موجودیت (بخش ۵.۳ سند)
STRONG_SCHEMES = {"orcid", "doi"}
AUTO_THRESHOLD = 0.72


def create_resolution_cases(db: Session) -> dict:
    """نامزدیابی تطبیق: شواهد قوی → ادغام خودکار؛ شواهد کمکی → پروندهٔ انسانی."""
    from ..models import ResearchProfile as RP
    persons = db.query(SemanticEntity).filter(
        SemanticEntity.kind == "Person", SemanticEntity.status == "active").all()
    ident: dict[str, dict[str, list[str]]] = {}
    for row in db.query(EntityIdentifier).filter(EntityIdentifier.scheme.in_(STRONG_SCHEMES)).all():
        ident.setdefault(row.entity_id, {}).setdefault(row.scheme, []).append(row.value.lower())
    faculty: dict[str, str] = {}
    for pr in db.query(RP).all():
        faculty[str(pr.user_id)] = normalize_text(pr.faculty_name or "")
    stats = {"auto_merged": 0, "pending": 0, "considered": 0}
    for i, a in enumerate(persons):
        for b in persons[i + 1:]:
            stats["considered"] += 1
            strong = False
            for scheme in STRONG_SCHEMES:
                va = set(ident.get(a.id, {}).get(scheme, []))
                vb = set(ident.get(b.id, {}).get(scheme, []))
                if va & vb:
                    strong = True
            sim = name_similarity(a.display_name, b.display_name)
            fac = faculty.get(a.ref_id or "") and faculty.get(a.ref_id or "") == faculty.get(b.ref_id or "")
            existing = db.query(ResolutionCase).filter(
                ((ResolutionCase.entity_a_id == a.id) & (ResolutionCase.entity_b_id == b.id)) |
                ((ResolutionCase.entity_a_id == b.id) & (ResolutionCase.entity_b_id == a.id))).one_or_none()
            if existing:
                continue
            if strong or sim >= AUTO_THRESHOLD:
                score = 1.0 if strong else round(sim, 3)
                case = ResolutionCase(entity_a_id=a.id, entity_b_id=b.id, score=score,
                                      evidence=[{"kind": "strong_identifier" if strong else "name_similarity+faculty",
                                                 "score": score}])
                if strong:
                    case.decision = "auto_merged"
                db.add(case)
                db.flush()
                if strong:
                    canonical, absorbed = (a, b) if (a.created_at or now_utc()) <= (b.created_at or now_utc()) else (b, a)
                    merge_entities(db, canonical, absorbed, None, case.id)
                    stats["auto_merged"] += 1
                else:
                    stats["pending"] += 1
    return stats


def merge_entities(db: Session, canonical: SemanticEntity, absorbed: SemanticEntity,
                   user: User | None, case_id: int | None = None) -> MergeOperation:
    """ادغام قابل بازگشت: انتقال ادعاها و شناسه‌ها با ثبت کامل برای تفکیک."""
    moved_claims = []
    for cl in db.query(RelationAssertion).filter(RelationAssertion.subject_entity_id == absorbed.id).all():
        moved_claims.append({"id": cl.id, "field": "subject", "from": absorbed.id})
        cl.subject_entity_id = canonical.id
    for cl in db.query(RelationAssertion).filter(RelationAssertion.object_entity_id == absorbed.id).all():
        moved_claims.append({"id": cl.id, "field": "object", "from": absorbed.id})
        cl.object_entity_id = canonical.id
    moved_ids = []
    for row in db.query(EntityIdentifier).filter(EntityIdentifier.entity_id == absorbed.id).all():
        dup = db.query(EntityIdentifier).filter(
            EntityIdentifier.entity_id == canonical.id, EntityIdentifier.scheme == row.scheme,
            EntityIdentifier.value == row.value).one_or_none()
        if dup:
            db.delete(row)
        else:
            row.entity_id = canonical.id
        moved_ids.append({"scheme": row.scheme, "value": row.value})
    db.flush()
    # حذف ادعاهای تکراریِ پس از ادغام (یکتایی subject+predicate+object+origin+source)
    seen_key = set()
    for cl in db.query(RelationAssertion).filter(
            (RelationAssertion.subject_entity_id == canonical.id) |
            (RelationAssertion.object_entity_id == canonical.id)).all():
        key = (cl.subject_entity_id, cl.predicate_code, cl.object_entity_id, cl.origin,
               cl.source_system, cl.rule_or_model_version)
        if key in seen_key:
            db.delete(cl)
        else:
            seen_key.add(key)
    absorbed.status = "merged"
    absorbed.merged_into = canonical.id
    op = MergeOperation(case_id=case_id, canonical_entity_id=canonical.id,
                        absorbed_entity_id=absorbed.id, action="merge",
                        payload={"moved_claims": moved_claims, "moved_identifiers": moved_ids},
                        created_by=user.id if user else None)
    db.add(op)
    db.add(EventLog(type="semantic_outbox", payload={"event": "entity_merged",
                                                     "canonical": canonical.id, "absorbed": absorbed.id}))
    db.flush()
    return op


def decide_case(db: Session, case_id: int, decision: str, user: User | None, reason: str = "") -> dict:
    case = db.get(ResolutionCase, case_id)
    if not case:
        raise ValueError("پرونده یافت نشد")
    if decision not in ("merge", "separate"):
        raise ValueError("تصمیم نامعتبر")
    a = resolve_entity(db, case.entity_a_id)
    b = resolve_entity(db, case.entity_b_id)
    if not a or not b or a.id == b.id:
        case.decision, case.reason = "separate", reason or "موجودیت‌ها یکسان‌اند"
        case.decided_by, case.decided_at = user.id if user else None, now_utc()
        db.flush()
        return {"case_id": case.id, "decision": case.decision}
    if decision == "merge":
        canonical = a if (a.created_at or now_utc()) <= (b.created_at or now_utc()) else b
        absorbed = b if canonical.id == a.id else a
        merge_entities(db, canonical, absorbed, user, case.id)
        case.decision = "merged"
    else:
        case.decision = "separate"
    case.reason = reason
    case.decided_by = user.id if user else None
    case.decided_at = now_utc()
    db.flush()
    return {"case_id": case.id, "decision": case.decision}


# ============================================================ پیشنهادها با دلیل و شواهد (بخش ۸–۹ سند)
def recommend_supervisors(db: Session, topic_text: str, field: str = "",
                          skills: list | None = None) -> dict:
    """پیشنهاد استاد راهنما — شروط اولیه پیش از رتبه‌بندی؛ خروجی با دلیل و نسخه.

    امتیاز، احتمال موفقیت نیست؛ ظرفیت بدون داده معتبر «نامشخص» نمایش داده می‌شود و
    پذیرش نهایی تنها از مسیر رسمی اعلام آمادگی در سامانه انجام می‌شود.
    """
    rebuild_projection(db)
    skills = [s for s in (skills or []) if str(s).strip()]
    profs = db.query(User).filter(User.is_active).all()
    profs = [p for p in profs if "professor" in (p.roles or [])]
    from ..models import Project as ProjectModel, ResearchProfile as RP
    profiles = {pr.user_id: pr for pr in db.query(RP).all()}
    q_tokens = set(tokenize(topic_text)) | set(tokenize(field)) | {normalize_text(s) for s in skills}

    # مفاهیم موضوع از واژگان (مترادف‌ها هم دیده می‌شوند)
    topic_concepts: set[str] = set()
    for c in db.query(SemanticConcept).all():
        terms = {normalize_text(c.name_fa), normalize_text(c.name_en)} | {normalize_text(s) for s in c.synonyms or []}
        if any(t and (t in q_tokens or any(t in tok for tok in q_tokens)) for t in terms if t):
            topic_concepts.add(c.id)

    results = []
    for p in profs:
        pe = _person_entity(db, p.id)
        if not pe or pe.id not in _projection["adj"]:
            continue
        pr = profiles.get(p.id)
        concept_names: set[str] = set()
        concept_ids: set[str] = set()
        skill_names: set[str] = set()
        research_counts: dict[str, int] = {}
        # شمارش تجمیعی امن: ادعاهای حساس فقط «شمرده» می‌شوند، محتوایشان هرگز نمایش داده نمی‌شود
        for e in _projection["adj"].get(pe.id, []):
            other = _projection["ent"].get(e["other"])
            if not other:
                continue
            if e["pred"] in ("EXPERT_IN", "INTERESTED_IN") and other["kind"] == "Concept":
                concept_names.add(other["name"])
                concept_ids.add(e["other"])
            if e["pred"] == "HAS_SKILL" and other["kind"] == "Skill":
                skill_names.add(other["name"])
            if e["pred"] == "RESEARCHED_ON" and other["kind"] == "Concept":
                research_counts[other["name"]] = research_counts.get(other["name"], 0) + 1
        all_terms = {normalize_text(x) for x in concept_names | skill_names}
        # اجزای امتیاز
        concept_fit = jaccard(q_tokens, all_terms) if q_tokens and all_terms else 0.0
        shared_c = topic_concepts & concept_ids
        concept_fit = max(concept_fit, min(len(shared_c) / max(len(topic_concepts), 1), 1.0) if topic_concepts else 0.0)
        skill_fit = (len({normalize_text(s) for s in skills} & {normalize_text(x) for x in skill_names})
                     / max(len(skills), 1)) if skills else 0.0
        graph_fit = min(len(research_counts) / 3.0, 1.0)
        recency = 0.3
        if pr and pr.updated_at:
            upd = pr.updated_at.replace(tzinfo=None)
            days = (now_utc().replace(tzinfo=None) - upd).days
            recency = 1.0 if days <= 90 else 0.5
        score = round(0.45 * concept_fit + 0.20 * skill_fit + 0.25 * graph_fit + 0.10 * recency, 3)
        if score < 0.05 and not shared_c:
            continue
        # شروط رسمی: ظرفیت — بدون داده معتبر → نامشخص
        capacity, cap_status = pr.capacity if pr else 0, "unknown"
        if pr and (pr.capacity or 0) > 0:
            active_leads = db.query(ProjectModel).filter(
                ProjectModel.lead_professor_id == p.id, ProjectModel.status == "active").count()
            capacity = max(pr.capacity - active_leads, 0)
            cap_status = "known"
        top_research = sorted(research_counts.items(), key=lambda x: -x[1])[:2]
        expl = "به دلیل "
        if shared_c:
            expl += "تناسب موضوعی مستقیم با تخصص اعلام‌شده"
            if top_research:
                expl += " و " + " و ".join(f"{n} پژوهش مرتبط با «{t}»" for t, n in top_research)
        elif top_research:
            expl += " و ".join(f"{n} پژوهش مرتبط با «{t}»" for t, n in top_research)
        else:
            expl += "هم‌پوشانی مفاهیم و مهارت‌های اعلام‌شده"
        expl += " پیشنهاد شده است. "
        expl += "ظرفیت راهنمایی: نامشخص (اطلاعات به‌روز در دسترس نیست)." if cap_status == "unknown" \
            else f"ظرفیت راهنمایی باقی‌مانده: {capacity} پروژه."
        results.append({
            "user_id": p.id, "name": p.display_name,
            "faculty": (pr.faculty_name if pr else "") or "",
            "score": score, "capacity_status": cap_status, "capacity": capacity,
            "components": {"concept": round(concept_fit, 3), "skill": round(skill_fit, 3),
                           "graph": round(graph_fit, 3), "recency": recency},
            "shared_concepts": sorted((_projection["ent"][c]["name"] for c in shared_c if c in _projection["ent"]))[:4],
            "explanation": expl,
        })
    results.sort(key=lambda x: (-x["score"], x["name"]))
    return {
        "algorithm_version": RECOMMEND_VERSION,
        "preconditions": {"checked": ["نقش استاد", "حساب فعال", "ظرفیت در صورت ثبت"],
                          "note": "ظرفیت بدون دادهٔ معتبر «نامشخص» نمایش داده می‌شود"},
        "candidates": results[:8],
        "note": "این پیشنهاد تصمیم نهایی نیست؛ پذیرش فقط از مسیر رسمی اعلام آمادگی و توافق‌نامه انجام می‌شود.",
    }


def collaboration_candidates(db: Session, user: User) -> dict:
    """نامزدهای همکاری برای شخصِ کاربر فعلی — فقط روابط استنتاجیِ ثبت‌شده با شواهد."""
    rebuild_projection(db)
    pe = _person_entity(db, user.id)
    if not pe:
        return {"candidates": [], "version": INFERENCE_VERSIONS["R2"]}
    out = []
    for e in visible_adj(user, pe.id):
        if e["pred"] != "CANDIDATE_COLLABORATOR":
            continue
        other = _projection["ent"].get(e["other"])
        if not other:
            continue
        shared = []
        for ev in e.get("evidence_ref", []) if isinstance(e.get("evidence_ref"), list) else []:
            if isinstance(ev, dict) and ev.get("kind") == "shared_concepts":
                shared = ev.get("names", [])
        out.append({"user_id": other.get("ref_id"), "name": other["name"],
                    "confidence": e["conf"], "shared_concepts": shared,
                    "review_status": e["review"]})
    return {"candidates": out, "version": INFERENCE_VERSIONS["R2"],
            "note": "خروجی الگوریتم است؛ به معنای همکاری واقعی یا تخصص تأییدشده نیست."}


def match_evidence(db: Session, prof: User, request_row) -> dict:
    """شواهد برازش برای کارت‌های استخر — رتبه‌بندی با توضیح؛ ثبت در گراف نمی‌شود."""
    rebuild_projection(db)
    pe = _person_entity(db, prof.id)
    re_ = db.query(SemanticEntity).filter(
        SemanticEntity.kind == "ResearchRequest", SemanticEntity.ref_table == "research_requests",
        SemanticEntity.ref_id == str(request_row.id)).one_or_none()
    if not pe or not re_:
        return {}
    prof_terms: set[str] = set()
    prof_concepts: list[str] = []
    for e in visible_adj(prof, pe.id):
        other = _projection["ent"].get(e["other"])
        if other and other["kind"] in ("Concept", "Skill"):
            prof_terms.add(normalize_text(other["name"]))
            if e["pred"] in ("EXPERT_IN", "INTERESTED_IN"):
                prof_concepts.append(other["name"])
    req_terms: set[str] = set()
    req_field = ""
    for e in visible_adj(prof, re_.id):
        other = _projection["ent"].get(e["other"])
        if not other:
            continue
        if e["pred"] == "REQUIRES_SKILL":
            req_terms.add(normalize_text(other["name"]))
        if e["pred"] == "ABOUT_FIELD":
            req_terms.add(normalize_text(other["name"]))
            req_field = other["name"]
    shared = prof_terms & req_terms
    skill_shared = {normalize_text(s) for s in (request_row.skills or [])} & prof_terms
    all_req = req_terms | {normalize_text(s) for s in (request_row.skills or [])}
    score = round(len(shared) / max(len(all_req), 1), 3) if all_req else 0.0
    if score < 0.01 and not shared:
        return {}
    why = []
    if req_field and req_field in prof_concepts:
        why.append(f"حوزهٔ «{req_field}» در تخصص/علاقهٔ شما")
    if skill_shared:
        why.append("مهارت‌های مشترک: " + "، ".join(sorted({s for s in (request_row.skills or [])
                                                           if normalize_text(s) in prof_terms}))[:120])
    paths = find_paths(db, prof, pe.id, re_.id, max_hops=3, limit=1)["paths"]
    path_fa = None
    if paths:
        step_names = [request_row.title] + [s["node"]["name"] for s in paths[0]["steps"]]
        path_fa = " ← ".join(step_names[:4])
    return {"score": score, "version": EVIDENCE_VERSION,
            "shared": sorted({x for x in shared})[:5], "why": why[:2], "path": path_fa,
            "note": "برازش الگوریتمی است؛ شروع همکاری نیازمند تصمیم انسانی است."}


def _person_entity(db: Session, user_id: int) -> SemanticEntity | None:
    ent = db.query(SemanticEntity).filter(
        SemanticEntity.kind == "Person", SemanticEntity.ref_table == "users",
        SemanticEntity.ref_id == str(user_id)).one_or_none()
    if ent:
        ent = resolve_entity(db, ent.id)
    return ent


def entity_by_user(db: Session, user_id: int) -> dict | None:
    """خلاصهٔ معنایی کاربر — برای کارت «پیوندهای معنایی» پروفایل."""
    pe = _person_entity(db, user_id)
    if not pe:
        return None
    rebuild_projection(db)
    e = _projection["ent"].get(pe.id, {})
    counts: dict[str, int] = {}
    top = []
    for edge in visible_adj(None, pe.id):
        counts[edge["pred"]] = counts.get(edge["pred"], 0) + 1
        other = _projection["ent"].get(edge["other"])
        if other and other["kind"] in ("Concept", "Skill") and edge["pred"] in ("EXPERT_IN", "INTERESTED_IN", "HAS_SKILL"):
            top.append({"name": other["name"], "pred": edge["pred"],
                        "pred_fa": PREDICATES[edge["pred"]][0], "origin": edge["origin"]})
    return {"entity_id": pe.id, "kind": e.get("kind"), "name": e.get("name"),
            "claim_counts": counts, "top_links": top[:8],
            "version": _projection["version"]}


# ============================================================ حاکمیت، تعارض و کیفیت (بخش ۱۵–۱۶ سند)
def detect_conflicts(db: Session) -> list[dict]:
    """تعارض منابع: یک (موضوع، رابطه) با مقاصد متفاوت از منابع متفاوت — هر دو ادعا با منشأ می‌مانند."""
    groups: dict[tuple, list[RelationAssertion]] = {}
    for cl in db.query(RelationAssertion).filter(RelationAssertion.origin == "asserted").all():
        groups.setdefault((cl.subject_entity_id, cl.predicate_code), []).append(cl)
    ents = {e.id: e for e in db.query(SemanticEntity).all()}
    conflicts = []
    for (sid, pred), cls in groups.items():
        objs = {(cl.object_entity_id, cl.source_system) for cl in cls}
        if len({o for o, _ in objs}) > 1 and len({s for _, s in objs}) > 1:
            conflicts.append({
                "subject": ents[sid].display_name if sid in ents else sid,
                "predicate": pred, "predicate_fa": PREDICATES.get(pred, (pred,))[0],
                "options": [{"object": ents[o].display_name if o in ents else o,
                             "source_system": s, "review": cl.review_status}
                            for o, s in sorted(objs) for cl in cls
                            if cl.object_entity_id == o and cl.source_system == s][:4],
                "resolved": False,
                "note": "تعارض حل‌نشده؛ هر دو ادعا با منشأ نگه داشته شده و جایگزین خاموش انجام نشده است.",
            })
    return conflicts


def quality_snapshot(db: Session) -> dict:
    from ..models import EntityIdentifier as EI, ResolutionCase as RC
    kinds: dict[str, int] = {}
    for e in db.query(SemanticEntity).all():
        kinds[e.kind] = kinds.get(e.kind, 0) + 1
    origins: dict[str, int] = {}
    for cl in db.query(RelationAssertion).all():
        origins[cl.origin] = origins.get(cl.origin, 0) + 1
    pend = db.query(RC).filter(RC.decision == "pending").count()
    ver = projection_version(db)
    last_int = db.query(IntegrationRun).order_by(IntegrationRun.created_at.desc()).first()
    last_inf = db.query(InferenceRun).order_by(InferenceRun.created_at.desc()).first()
    return {
        "entities": kinds, "claims_by_origin": origins,
        "identifiers": db.query(EI).count(),
        "pending_resolution_cases": pend,
        "conflicts": detect_conflicts(db),
        "projection": {"registry_version": ver, "built": _projection["version"],
                       "is_stale": _projection["version"] != ver,
                       "built_at": str(_projection["built_at"] or "")},
        "last_integration": {"id": last_int.id, "at": str(last_int.created_at), "stats": last_int.stats} if last_int else None,
        "last_inference": {"rule": last_inf.rule_code, "version": last_inf.rule_version,
                           "at": str(last_inf.created_at), "stats": last_inf.stats} if last_inf else None,
        "vocab_version": VOCAB_VERSION,
        "system_version": APP_VERSION,
    }
