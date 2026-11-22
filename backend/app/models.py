"""مدل داده پژوهشیار۳۶۰"""
from sqlalchemy import (
    JSON, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)

from .core.database import Base
from .core.utils import now_utc


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=True)  # برای کاربر صرفاً SSO خالی است
    display_name = Column(String(120), nullable=False)
    roles = Column(JSON, default=list)  # student | professor | research_manager | system_admin
    sso_issuer = Column(String(400), nullable=True, index=True)  # اتصال هویت مرکزی: issuer
    sso_sub = Column(String(128), nullable=True, index=True)     # و sub
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)

    __table_args__ = (UniqueConstraint("sso_issuer", "sso_sub", name="uq_sso_identity"),)


class SsoSettings(Base):
    __tablename__ = "sso_settings"
    id = Column(Integer, primary_key=True, default=1)
    enabled = Column(Boolean, default=False)
    issuer = Column(String(400), default="")          # مثال: http://188.212.96.235:8086 (پرتال دانشجویار۳۶۰)
    client_id = Column(String(200), default="pajouhyar360")
    client_type = Column(String(20), default="public")   # public+PKCE یا confidential
    client_secret = Column(String(400), default="")      # فقط برای confidential
    redirect_uri = Column(String(400), default="")       # باید کاراکتربه‌کاراکتر در clients.json ثبت شود
    post_logout_redirect_uri = Column(String(400), default="")
    button_label = Column(String(120), default="")       # برچسب دکمهٔ ورود SSO
    scope = Column(String(200), default="openid profile email")
    auto_create_users = Column(Boolean, default=False)
    default_roles = Column(JSON, default=lambda: ["student"])
    last_test_status = Column(String(400), default="")
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class ResearchProfile(Base):
    __tablename__ = "research_profiles"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    field_of_study = Column(String(120), default="")   # رشته
    faculty_name = Column(String(160), default="")     # دانشکده — برای دامنه‌بندی دید درخواست‌ها
    degree = Column(String(60), default="")            # مقطع
    interests = Column(JSON, default=list)             # علایق پژوهشی
    skills = Column(JSON, default=list)                # مهارت‌ها
    bio = Column(Text, default="")
    research_history = Column(Text, default="")        # سوابق (حساس — نمایش عمومی ندارد)
    publications = Column(JSON, default=list)          # مقالات و نمونه‌کارها (حساس)
    availability = Column(String(200), default="")     # زمان آزاد
    collaboration_type = Column(String(120), default="")  # نوع همکاری
    research_goal = Column(String(300), default="")    # هدف پژوهش
    expertise = Column(JSON, default=list)             # حوزه‌های تخصصی استاد
    methods_tools = Column(Text, default="")           # روش‌ها و ابزارهای استاد
    capacity = Column(Integer, default=0)              # ظرفیت پذیرش دانشجو
    conditions = Column(Text, default="")              # شرایط همکاری استاد
    academic_data = Column(JSON, default=dict)         # از زیرساخت دانشجو۳۶۰ (نمونه)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class Topic(Base):
    """بانک موضوعات: kind=topic موضوع پژوهشی | kind=template الگوی استاندارد تعریف موضوع"""
    __tablename__ = "topics"
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    kind = Column(String(20), default="topic")
    title = Column(String(300), nullable=False)
    field = Column(String(120), default="")
    problem_statement = Column(Text, default="")
    research_questions = Column(Text, default="")
    expected_output = Column(Text, default="")
    suggested_method = Column(Text, default="")
    required_skills = Column(JSON, default=list)
    required_data_equipment = Column(Text, default="")
    estimated_duration = Column(String(60), default="")
    team_size = Column(Integer, default=1)
    acceptance_terms = Column(Text, default="")
    funding_status = Column(String(120), default="")   # وضعیت تأمین مالی
    ethics_requirements = Column(Text, default="")     # الزامات اخلاق پژوهش
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)


class ResearchRequest(Base):
    """درخواست پژوهش دانشجو — چرخه تا اتصال به پروژه"""
    __tablename__ = "research_requests"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    summary = Column(Text, default="")                 # خلاصه قابل نمایش برای ایده محرمانه
    problem = Column(Text, default="")
    goals = Column(Text, default="")
    field = Column(String(120), default="")
    skills = Column(JSON, default=list)
    timeline = Column(String(200), default="")
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=True)  # منبع موضوع/الگو
    scope = Column(String(20), default="all")          # all | faculty | selected
    faculty_name = Column(String(160), default="")
    selected_professors = Column(JSON, default=list)   # برای scope=selected
    secret_details = Column(Text, default="")          # محرمانه — دسترسی با اجازه صاحب درخواست
    secret_shared_with = Column(JSON, default=list)    # شناسه کاربران مجاز به جزئیات محرمانه
    status = Column(String(40), default="draft", index=True)
    university_approval_required = Column(Boolean, default=False)
    current_offer_id = Column(Integer, ForeignKey("offers.id"), nullable=True)
    closed_reason = Column(String(400), default="")
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class Attachment(Base):
    __tablename__ = "attachments"
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    orig_name = Column(String(300), default="")
    stored_name = Column(String(120), nullable=False)  # نام تصادفی غیرقابل حدس
    size = Column(Integer, default=0)
    content_type = Column(String(160), default="")
    request_id = Column(Integer, ForeignKey("research_requests.id"), nullable=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)


class Offer(Base):
    """اعلام آمادگی استاد برای همکاری"""
    __tablename__ = "offers"
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("research_requests.id"), nullable=False, index=True)
    professor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(Text, default="")
    conditions = Column(Text, default="")
    status = Column(String(30), default="sent", index=True)
    # sent | viewed | in_dialogue | accepted | converted_to_project | rejected_by_student | withdrawn | superseded
    created_at = Column(DateTime(timezone=True), default=now_utc)


class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("research_requests.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    professor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (UniqueConstraint("request_id", "professor_id", name="uq_conv_request_prof"),)


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    kind = Column(String(20), default="text")  # text | file | meeting | meeting_result
    body = Column(Text, default="")
    attachment_id = Column(Integer, ForeignKey("attachments.id"), nullable=True)
    is_flagged = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=now_utc)


class Agreement(Base):
    """توافق‌نامه همکاری — پیش از تشکیل پروژه، امضای دوطرفه الزامی است"""
    __tablename__ = "agreements"
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("research_requests.id"), unique=True, nullable=False)
    offer_id = Column(Integer, ForeignKey("offers.id"), nullable=False)
    title = Column(String(300), default="")
    responsibilities = Column(Text, default="")
    timeline = Column(Text, default="")
    deliverables = Column(Text, default="")
    confidentiality = Column(Text, default="")
    ip_ownership = Column(Text, default="")
    student_signed_at = Column(DateTime(timezone=True), nullable=True)
    professor_signed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)


class Project(Base):
    """پروژه مشترک — دقیقاً یک پروژه برای هر درخواست (قید یکتایی)"""
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("research_requests.id"), unique=True, nullable=False)
    title = Column(String(300), nullable=False)
    lead_professor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(20), default="active")  # active | closing | closed
    closed_reason = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=now_utc)
    closed_at = Column(DateTime(timezone=True), nullable=True)


class ProjectMember(Base):
    __tablename__ = "project_members"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(30), default="member")  # lead | student | advisor | member
    added_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    added_at = Column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_member"),)


class ProjectTask(Base):
    __tablename__ = "project_tasks"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, default="")
    assignee_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    due_date = Column(Date, nullable=True)
    status = Column(String(20), default="todo")  # todo | doing | done
    created_at = Column(DateTime(timezone=True), default=now_utc)


class ProjectMeeting(Base):
    __tablename__ = "project_meetings"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    title = Column(String(300), default="")
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    minutes = Column(Text, default="")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)


class ProgressReport(Base):
    __tablename__ = "progress_reports"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    percent = Column(Integer, default=0)
    note = Column(Text, default="")
    feedback = Column(Text, default="")   # بازخورد استاد
    created_at = Column(DateTime(timezone=True), default=now_utc)


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String(40), default="")
    title = Column(String(300), default="")
    body = Column(Text, default="")
    link = Column(String(300), default="")
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=now_utc)


class EventLog(Base):
    """رخدادهای سامانه — برای اعلان‌ها، تحلیل‌ها و مصرف سایر سامانه‌های اکوسیستم"""
    __tablename__ = "event_logs"
    id = Column(Integer, primary_key=True)
    type = Column(String(50), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    payload = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=now_utc, index=True)


class AiSuggestionLog(Base):
    __tablename__ = "ai_suggestion_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    kind = Column(String(50), default="")
    input_json = Column(JSON, default=dict)
    output_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=now_utc)


# ============================================================
# لایه معنایی و گراف دانش — دفتر ثبت معتبر (بخش ۱۱.۳ سند):
# PostgreSQL/SQLite اینجا «منبع حقیقت» است؛ نمای گرافی فقط
# قابل بازسازی از همین دفتر است و هرگز خودش مرجع نمی‌شود.
# ============================================================

class SemanticEntity(Base):
    """موجودیت معنایی — با شناسه پایدار UUID و پیوند به رکورد مرجع (ref_table/ref_id).

    سامانه‌های مرجع مالک داده‌اند؛ اینجا فقط تصویر نسخه‌دار و قابل ردیابی نگه داشته می‌شود.
    """
    __tablename__ = "semantic_entities"
    id = Column(String(36), primary_key=True)          # UUID پایدار
    kind = Column(String(30), nullable=False, index=True)  # Person | Organization | AcademicUnit | Skill | Concept | Topic | ResearchRequest | ResearchProject | Publication
    ref_table = Column(String(60), default="")          # جدول سامانه مرجع (خالی برای مفاهیم واژگانی)
    ref_id = Column(String(60), default="")             # شناسه در سامانه مرجع
    display_name = Column(String(300), nullable=False)
    display_name_norm = Column(String(300), default="", index=True)
    summary = Column(Text, default="")
    status = Column(String(20), default="active", index=True)  # active | merged | archived
    merged_into = Column(String(36), nullable=True)     # ادغام — اشاره به موجودیت کانونی
    meta = Column(JSON, default=dict)                   # ویژگی‌های تکمیلی نسخه‌دار
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    created_at = Column(DateTime(timezone=True), default=now_utc)


class EntityIdentifier(Base):
    """شناسه موجودیت در منابع مختلف — شواهد قوی تطبیق (ORCID، DOI، شناسه مرجع، …)."""
    __tablename__ = "entity_identifiers"
    id = Column(Integer, primary_key=True)
    entity_id = Column(String(36), ForeignKey("semantic_entities.id"), nullable=False, index=True)
    scheme = Column(String(40), nullable=False)         # portal_uid | orcid | doi | hr_id | internal
    value = Column(String(400), nullable=False, index=True)
    source_system = Column(String(80), default="")
    confidence = Column(Float, default=1.0)
    created_at = Column(DateTime(timezone=True), default=now_utc)


class RelationAssertion(Base):
    """ادعای رابطه — با منشأ، اعتبار، اطمینان، سیاست دسترسی و وضعیت داوری (بخش ۳.۳ سند).

    origin: asserted (رسمی از مرجع) | extracted (استخراج از متن) | inferred (استنتاج قاعده/الگوریتم)
    روابط استنتاجی با رابطه رسمی اشتباه گرفته نمی‌شوند و قابل حذف/محاسبهٔ مجددند.
    """
    __tablename__ = "relation_assertions"
    id = Column(String(36), primary_key=True)           # UUID
    subject_entity_id = Column(String(36), ForeignKey("semantic_entities.id"), nullable=False, index=True)
    predicate_code = Column(String(40), nullable=False, index=True)
    object_entity_id = Column(String(36), ForeignKey("semantic_entities.id"), nullable=False, index=True)
    origin = Column(String(12), nullable=False, default="asserted")
    source_system = Column(String(80), default="pazhoheshyar-core")
    source_record_id = Column(String(36), nullable=True)   # پیوند به SourceRecord
    evidence_ref = Column(JSON, default=list)           # شواهد مسیر/رکورد (بدون محتوای حساس)
    confidence = Column(Float, nullable=True)
    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_to = Column(DateTime(timezone=True), nullable=True)
    observed_at = Column(DateTime(timezone=True), default=now_utc)
    access_policy = Column(String(20), default="public")   # public | internal | restricted
    rule_or_model_version = Column(String(60), default="")
    review_status = Column(String(20), default="approved")  # approved | pending | rejected
    payload = Column(JSON, default=dict)                # نقش، ترتیب نویسندگی، …
    created_at = Column(DateTime(timezone=True), default=now_utc)


class SemanticConcept(Base):
    """واژگان کنترل‌شده (SKOS-سازگار): شناسه پایدار، نام دوزبانه، مترادف، سلسله‌مراتب، نسخه."""
    __tablename__ = "semantic_concepts"
    id = Column(String(36), primary_key=True)
    name_fa = Column(String(200), nullable=False)
    name_en = Column(String(200), default="")
    definition = Column(Text, default="")
    synonyms = Column(JSON, default=list)               # مترادف‌ها (فارسی/انگلیسی/اختصار)
    broader_id = Column(String(36), nullable=True)      # مفهوم بالادست
    status = Column(String(20), default="approved")     # approved | draft
    version = Column(String(20), default="voc-1.0.0")
    source_system = Column(String(80), default="pazhoheshyar-core")
    created_at = Column(DateTime(timezone=True), default=now_utc)


class SourceRecord(Base):
    """رکورد خام دریافتی — ثبت منشأ پیش از هر تبدیل (گام ۲ خط پردازش، بخش ۵.۱ سند)."""
    __tablename__ = "source_records"
    id = Column(String(36), primary_key=True)
    source_system = Column(String(80), nullable=False)  # pazhoheshyar-core | hr-import | portal | …
    record_type = Column(String(60), default="")
    external_id = Column(String(200), default="")
    raw = Column(JSON, default=dict)                    # بار خام (بدون فیلد حساسِ غیرضروری)
    received_at = Column(DateTime(timezone=True), default=now_utc)


class ResolutionCase(Base):
    """پرونده تطبیق موجودیت — تصمیم سه‌سطحی: خودکار (شواهد بسیار قوی) | انسانی | عدم تطبیق."""
    __tablename__ = "resolution_cases"
    id = Column(Integer, primary_key=True)
    entity_a_id = Column(String(36), ForeignKey("semantic_entities.id"), nullable=False)
    entity_b_id = Column(String(36), ForeignKey("semantic_entities.id"), nullable=False)
    score = Column(Float, default=0.0)
    evidence = Column(JSON, default=list)               # فهرست شواهد و دلیل امتیاز
    decision = Column(String(20), default="pending", index=True)  # pending | merged | separate | auto_merged
    decided_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    reason = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=now_utc)


class MergeOperation(Base):
    """تاریخچه ادغام و تفکیک — ادغام قابل بازگشت است (بخش ۵.۳ سند)."""
    __tablename__ = "merge_operations"
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, nullable=True)
    canonical_entity_id = Column(String(36), nullable=False)
    absorbed_entity_id = Column(String(36), nullable=False)
    action = Column(String(20), default="merge")        # merge | separate
    payload = Column(JSON, default=dict)                # نگاشت رکوردهای منتقل‌شده برای تفکیک
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)


class InferenceRun(Base):
    """اجرای قاعدهٔ استنتاج — نسخه‌دار، آمارپذیر و ابطال‌پذیر (بخش ۶.۱ سند)."""
    __tablename__ = "inference_runs"
    id = Column(String(36), primary_key=True)
    rule_code = Column(String(40), nullable=False)
    rule_version = Column(String(40), default="")
    status = Column(String(20), default="completed")    # completed | failed | disabled
    stats = Column(JSON, default=dict)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)


class IntegrationRun(Base):
    """اجرای ورود داده از منبع — وضعیت و آمار برای پایش عقب‌ماندگی همگام‌سازی."""
    __tablename__ = "integration_runs"
    id = Column(String(36), primary_key=True)
    source_system = Column(String(80), nullable=False)
    status = Column(String(20), default="completed")
    stats = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=now_utc)


# ============================================================
# فضای پژوهش تیمی — نگارش مشترک سند پژوهشی با قالب‌های استاندارد
# (IEEE کنفرانس/مجله، اسپرینگر LNCS/مقاله، APA، پایان‌نامهٔ فارسی)
# ============================================================

class ResearchDoc(Base):
    """سند پژوهشی تیمی — دانشجو و استاد و اعضای گروه، یک سند را با نقش مشترک می‌نویسند."""
    __tablename__ = "research_docs"
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)       # مسئول سند
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, index=True)   # پیوند اختیاری به پروژهٔ رسمی
    title = Column(String(300), nullable=False)
    language = Column(String(10), default="fa")            # fa | en
    template = Column(String(40), default="ieee-conference", index=True)
    status = Column(String(30), default="draft", index=True)   # draft | in_review | revised | approved | published
    abstract = Column(Text, default="")
    keywords = Column(JSON, default=list)
    venue_note = Column(String(300), default="")           # مقصد ارسال (نام کنفرانس/مجله)
    semantic_entity_id = Column(String(36), nullable=True)  # موجودیت «اثر علمی» پس از انتشار در شبکهٔ دانش
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class DocMember(Base):
    """عضو فضای پژوهش — lead مسئول سند | writer نویسنده | reviewer داور | observer ناظر"""
    __tablename__ = "doc_members"
    id = Column(Integer, primary_key=True)
    doc_id = Column(Integer, ForeignKey("research_docs.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(20), default="writer")            # lead | writer | reviewer | observer
    added_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    added_at = Column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (UniqueConstraint("doc_id", "user_id", name="uq_doc_member"),)


class DocSection(Base):
    """بخش سند — نگارش مشترک با قفل خوش‌بینانه (version_no) و نویسندهٔ مسئول هر بخش"""
    __tablename__ = "doc_sections"
    id = Column(Integer, primary_key=True)
    doc_id = Column(Integer, ForeignKey("research_docs.id"), nullable=False, index=True)
    ord = Column(Integer, default=0)                       # ترتیب در سند
    heading = Column(String(200), default="")
    body = Column(Text, default="")
    guidance = Column(Text, default="")                    # راهنمای قالب برای همان بخش
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    version_no = Column(Integer, default=1)                # قفل خوش‌بینانه ویرایش هم‌زمان
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class DocVersion(Base):
    """نسخهٔ ثبت‌شدهٔ کل سند — عکس فوری برای تاریخچه و بازگشت"""
    __tablename__ = "doc_versions"
    id = Column(Integer, primary_key=True)
    doc_id = Column(Integer, ForeignKey("research_docs.id"), nullable=False, index=True)
    label = Column(String(200), default="")
    snapshot = Column(JSON, default=dict)                  # بخش‌ها + انتزاع + کلیدواژه‌ها
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)


class DocComment(Base):
    """گفت‌وگوی داوری روی سند/بخش — با وضعیت حل‌شده"""
    __tablename__ = "doc_comments"
    id = Column(Integer, primary_key=True)
    doc_id = Column(Integer, ForeignKey("research_docs.id"), nullable=False, index=True)
    section_id = Column(Integer, ForeignKey("doc_sections.id"), nullable=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    body = Column(Text, default="")
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=now_utc)


class DocReference(Base):
    """مرجع کتاب‌شناختی سند — خروجی فرمت‌بندی به سه سبک IEEE/اسپرینگر/APA"""
    __tablename__ = "doc_references"
    id = Column(Integer, primary_key=True)
    doc_id = Column(Integer, ForeignKey("research_docs.id"), nullable=False, index=True)
    authors = Column(Text, default="")                     # نویسندگان به همان صورت ثبت
    title = Column(String(400), nullable=False)
    venue = Column(String(300), default="")                # مجله/کنفرانس
    year = Column(String(10), default="")
    doi = Column(String(120), default="")
    url = Column(String(400), default="")
    note = Column(Text, default="")
    added_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)

