"""داده آزمایشی — صریحاً برچسب‌گذاری‌شده؛ هیچ‌کدام اتصال واقعی یا هوش مصنوعی عملیاتی نیست"""
from .core.security import hash_password
from .core.utils import log_event
from .models import Agreement, Conversation, Message, Offer, ResearchProfile, ResearchRequest, SsoSettings, Topic, User

DEMO_LABEL = "داده آزمایشی"


def seed(db) -> None:
    def get_user(username, display_name, roles, password="12345678"):
        u = db.query(User).filter(User.username == username).one_or_none()
        if not u:
            u = User(username=username, display_name=display_name, roles=roles,
                     password_hash=hash_password(password))
            db.add(u)
            db.flush()
        return u

    s1 = get_user("student1", "مریم احمدی", ["student"])
    s2 = get_user("student2", "علی رضایی", ["student"])
    p1 = get_user("prof1", "دکتر سارا موسوی", ["professor"])
    p2 = get_user("prof2", "دکتر رضا کریمی", ["professor"])
    m1 = get_user("manager1", "حمید عباسی (مدیر پژوهش)", ["research_manager"])
    a1 = get_user("admin1", "مدیر سامانه", ["system_admin"])

    def get_profile(user, **kw):
        p = db.query(ResearchProfile).filter(ResearchProfile.user_id == user.id).one_or_none()
        if not p:
            p = ResearchProfile(user_id=user.id, **kw)
            db.add(p)
        return p

    get_profile(s1, field_of_study="مهندسی کامپیوتر", faculty_name="دانشکده مهندسی کامپیوتر", degree="کارشناسی ارشد",
                interests=["پردازش زبان طبیعی", "یادگیری ماشین"], skills=["پایتون", "یادگیری ماشین", "پردازش متن فارسی"],
                availability="عصرها و تعطیلات آخر هفته", collaboration_type="دورکاری + جلسه حضوری هفتگی",
                research_goal="انتشار یک مقاله ژورنالی پیش از فارغ‌التحصیلی",
                research_history="—" + DEMO_LABEL,
                academic_data={"source": "daneshjoo360-demo", "gpa": 17.8, "passed_credits": 42,
                               "label": DEMO_LABEL})

    get_profile(p1, field_of_study="هوش مصنوعی", faculty_name="دانشکده مهندسی کامپیوتر",
                interests=["پردازش زبان طبیعی", "بازیابی اطلاعات"], expertise=["یادگیری ماشین", "پردازش زبان طبیعی"],
                skills=["پایتون", "یادگیری ماشین"], capacity=3,
                methods_tools="پایتون، PyTorch، HuggingFace — " + DEMO_LABEL,
                conditions="جلسه هفتگی، گزارش ماهانه — " + DEMO_LABEL)

    get_profile(p2, field_of_study="شبکه و امنیت", faculty_name="دانشکده مهندسی برق",
                interests=["شبکه‌های نرم‌افزارمحور"], expertise=["شبکه", "امنیت"], skills=["تحلیل ترافیک"],
                capacity=2, methods_tools=DEMO_LABEL, conditions=DEMO_LABEL)

    get_profile(s2, field_of_study="مهندسی صنایع", faculty_name="دانشکده صنایع", degree="کارشناسی",
                interests=["تحلیل داده آموزشی"], skills=["آمار", "اکسل"])

    def get_topic(owner, kind, title, **kw):
        t = db.query(Topic).filter(Topic.title == title).one_or_none()
        if not t:
            t = Topic(owner_id=owner.id, kind=kind, title=title, **kw)
            db.add(t)
            db.flush()
        return t

    get_topic(p1, "topic", "تشخیص احساسات در متون فارسی با یادگیری عمیق",
              field="هوش مصنوعی", problem_statement="کمبود مدل‌های دقیق تحلیل احساسات فارسی — " + DEMO_LABEL,
              research_questions="کدام معماری برای فارسی بهینه است؟", expected_output="مدل + مقاله",
              suggested_method="فاین‌تیون ترنسفورمرها", required_skills=["پایتون", "یادگیری ماشین"],
              required_data_equipment="دیتاست برچسب‌خورده فارسی (نمونه)", estimated_duration="۶ ماه",
              team_size=2, acceptance_terms="گذراندن درس یادگیری ماشین", funding_status="بدون بودجه (نمونه)",
              ethics_requirements="مصون از داده شخصی")
    get_topic(p1, "template", "الگوی استاندارد: پروژه یادگیری ماشین کاربردی",
              field="هوش مصنوعی", problem_statement="قالب تعریف موضوع — " + DEMO_LABEL,
              expected_output="مخزن کد + گزارش", required_skills=["پایتون"], estimated_duration="۴-۶ ماه",
              acceptance_terms=DEMO_LABEL, ethics_requirements=DEMO_LABEL)
    get_topic(p2, "topic", "شناسایی ترافیک مخرب در شبکه‌های نرم‌افزارمحور",
              field="شبکه", problem_statement=DEMO_LABEL, required_skills=["تحلیل ترافیک"],
              estimated_duration="۵ ماه")

    if not db.query(ResearchRequest).filter(ResearchRequest.title.like("%پاسخ‌های دانشجویی%")).one_or_none():
        r1 = ResearchRequest(
            student_id=s1.id, title="دستیار هوشمند پاسخ به پرسش‌های دانشجویی مبتنی بر بازیابی اطلاعات",
            summary="ساخت دستیاری که بر اساس اسناد آیین‌نامه‌ها پاسخ دقیق با ارجاع بدهد. (" + DEMO_LABEL + ")",
            problem="پرسش‌های تکراری آموزش از منابع پراکنده پاسخ داده می‌شود و پاسخ‌ها گاه نادرست‌اند. " + DEMO_LABEL,
            goals="دستیار پرسش‌وپاسخ با ارجاع به منبع و ارزیابی دقت. " + DEMO_LABEL,
            field="هوش مصنوعی", skills=["پایتون", "یادگیری ماشین", "پردازش متن فارسی"],
            timeline="۴ ماه توسعه + ۲ ماه ارزیابی", scope="all", secret_details="ایده محرمانه: ادغام با سامانه آموزشیار۳۶۰ — " + DEMO_LABEL,
            status="published", university_approval_required=True,
        )
        db.add(r1)
        db.flush()
        o1 = Offer(request_id=r1.id, professor_id=p1.id,
                   message="تخصص ما دقیقاً در همین حوزه است؛ چند مقاله مرتبط داریم. " + DEMO_LABEL,
                   conditions="جلسه هفتگی و گزارش ماهانه. " + DEMO_LABEL, status="sent")
        db.add(o1)
        db.flush()
        r1.status = "offers_received"
        conv = Conversation(request_id=r1.id, student_id=s1.id, professor_id=p1.id)
        db.add(conv)
        db.flush()
        db.add(Message(conversation_id=conv.id, sender_id=p1.id, kind="text",
                       body="سلام؛ موضوع جالبی است. لطفاً درباره داده در دسترس توضیح دهید. " + DEMO_LABEL))
        db.add(Message(conversation_id=conv.id, sender_id=s1.id, kind="text",
                       body="سلام استاد؛ دیتاست نمونه دانشگاه داریم. " + DEMO_LABEL))
        log_event(None, "seed_demo", None, {"label": DEMO_LABEL}) if False else None
    if not db.query(ResearchRequest).filter(ResearchRequest.title.like("%تحلیل کیفی آموزش%")).one_or_none():
        db.add(ResearchRequest(
            student_id=s2.id, title="تحلیل کیفی آموزش بر اساس بازخورد دروس",
            summary=DEMO_LABEL, problem="پیش‌نویس آزمایشی — " + DEMO_LABEL, goals=DEMO_LABEL,
            field="تحلیل داده", skills=["آمار"], scope="faculty", faculty_name="دانشکده صنایع", status="draft",
        ))

    if not db.get(SsoSettings, 1):
        db.add(SsoSettings(id=1, enabled=False, issuer="https://sso.example.ac.ir/realms/daneshjoo360",
                           client_id="pajoohesh-yar360", redirect_uri="http://localhost:3000/sso/callback"))
    db.commit()
