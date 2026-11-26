import React, { useEffect, useState } from 'react'
import { useAuth } from '../auth.jsx'
import { api, toFa, fmtDateTime } from '../api.js'
import { CreateForm, RecordDetail, STATUS_BADGE, INTERVAL_FA } from './practicumShared.jsx'

/* کارآموزی — صفحهٔ جدا از درس‌پروژه: پس از پذیرش استاد و تعیین زمان‌بندی (روزانه/هفتگی/
   دوهفته‌یکبار)، دانشجو از لحظهٔ پذیرش گزارش پیشرفت را بدون انتظار تأیید مرحله‌ای می‌فرستد؛
   استاد هر گزارش را با طیف لیکرت ۰ تا ۴ امتیاز می‌دهد و سرجمع امتیازها (سقف ۲۰) نمرهٔ از ۲۰ است */
export default function Internship() {
  const { user } = useAuth()
  const [meta, setMeta] = useState(null)
  const [records, setRecords] = useState([])
  const [openId, setOpenId] = useState(null)

  const isStudent = (user?.roles || []).includes('student')
  const isManager = (user?.roles || []).some(r => ['research_manager', 'system_admin'].includes(r))
  const load = () => {
    const path = isStudent ? '/practicum/mine' : isManager ? '/practicum/all' : '/practicum/supervised'
    api(path).then(rows => setRecords(rows.filter(r => r.course_type === 'internship'))).catch(e => alert(e.message))
    api('/practicum/meta').then(setMeta).catch(() => {})
  }
  useEffect(() => { load() }, [])
  if (openId) return <RecordDetail id={openId} onBack={() => { setOpenId(null); load() }} user={user} />

  const internshipAllowed = (meta?.courses || []).some(c => c.key === 'internship' && c.allowed)

  return (
    <>
      <div className="card">
        <h3>🏭 کارآموزی — گزارش پیشرفت با طیف لیکرت</h3>
        {meta?.my_degree ? (
          <div className="demo-banner">
            <b>🎓 مقطع شما: {meta.degree_fa}</b>
            {internshipAllowed
              ? <> — درس کارآموزی برای مقطع شما <b>فعال</b> است.</>
              : <> — درس کارآموزی برای مقطع شما ارائه نمی‌شود (مخصوص کاردانی و کارشناسی)؛ درس عملی شما «تحقیق و ارائه» است.</>}
          </div>
        ) : (
          <div className="error-box">مقطع تحصیلی در پروفایل شما ثبت نشده — از «پروفایل پژوهشی» مقطع را انتخاب کنید.</div>
        )}
        <div className="hint" style={{ marginTop: 8 }}>
          {meta?.internship_guidance || 'پس از ثبت کارآموزی، استاد مربوطه پذیرش و زمان‌بندی گزارش پیشرفت را تعیین می‌کند (روزانه، هفتگی یا دوهفته‌یکبار) و از لحظهٔ پذیرش، دانشجو طبق برنامه گزارش می‌فرستد. امتیاز هر گزارش ۰ تا ۴ است و سرجمع امتیازها (سقف ۲۰) نمرهٔ کارآموزی از ۲۰ می‌شود. حداقل ۵ گزارش پیشرفت در ترم لازم است.'}
        </div>
      </div>

      {isStudent && internshipAllowed && <CreateForm meta={meta} onDone={load} onlyType="internship" title="➕ ثبت کارآموزی جدید" />}
      {!isStudent && <div className="card"><h4>📥 کارآموزی‌های {isManager ? 'همهٔ دانشجویان' : 'تحت ارزیابی من'} ({toFa(records.length)}) — <a href="#/internship-dashboard" className="lnk">📊 گزارش کارآموزی‌ها</a></h4></div>}

      <div className="grid cols-2">
        {records.map(r => (
          <div key={r.id} className="card">
            <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap' }}>
              <h4 style={{ margin: 0 }}>🏭 {r.title}</h4>
              <span className={`badge ${STATUS_BADGE[r.status]}`}>{r.status_fa}</span>
            </div>
            <div className="hint" style={{ marginTop: 6 }}>
              {isStudent ? `استاد مربوطه: ${r.supervisor_name}` : `دانشجو: ${r.student_name}`}
              {r.semester ? ` · ${r.semester}` : ''}
            </div>
            {r.status === 'pending_acceptance' ? (
              <div className="hint">در انتظار پذیرش و تعیین زمان‌بندی توسط استاد مربوطه.</div>
            ) : (
              <>
                <div className="hint">
                  زمان‌بندی گزارش پیشرفت: <b>{INTERVAL_FA[r.report_interval] || 'هفتگی'}</b>
                  {r.accepted_at ? <> (از {fmtDateTime(r.accepted_at)})</> : null} ·
                  گزارش‌ها: <b>{toFa(r.round_count)}</b> از حداقل {toFa(r.min_reports || 5)}
                  {(r.round_count || 0) >= (r.min_reports || 5) ? ' ✓ شرط حداقل کامل است' : ''}
                </div>
                <div className="hint">
                  امتیاز تجمعی لیکرت: <b>{toFa(r.current_score ?? 0)}</b> از سقف ۲۰
                  {(r.unscored_count || 0) > 0 && <> · {toFa(r.unscored_count)} گزارش در انتظار امتیاز استاد</>}
                </div>
              </>
            )}
            {r.final_score != null && <div className="hint">نمرهٔ نهایی کارآموزی: <b>{toFa(r.final_score)}</b> از ۲۰</div>}
            <div className="row" style={{ gap: 6, marginTop: 8 }}>
              <button className="btn small" onClick={() => setOpenId(r.id)}>نمایش گزارش‌ها و امتیازها</button>
            </div>
          </div>
        ))}
        {records.length === 0 && (
          <div className="fancy-empty" style={{ gridColumn: '1 / -1' }}>
            <div className="big">🏭</div>
            {isStudent
              ? 'هنوز کارآموزی ثبت نکرده‌اید — با فرم بالای صفحه، استاد مربوطه و محل کارآموزی را ثبت کنید.'
              : 'هنوز کارآموزی‌ای برای ارزیابی دارید نیست.'}
          </div>
        )}
      </div>
    </>
  )
}
