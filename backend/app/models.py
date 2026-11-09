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
    issuer = Column(String(400), default="")          # مثال: https://sso.univ.ac.ir/realms/daneshjoo360
    client_id = Column(String(200), default="pajoohesh-yar360")
    client_secret = Column(String(400), default="")
    redirect_uri = Column(String(400), default="http://localhost:3000/sso/callback")
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
