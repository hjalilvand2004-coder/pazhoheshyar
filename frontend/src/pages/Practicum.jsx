import React, { useEffect, useState } from 'react'
import { useAuth } from '../auth.jsx'
import { api, toFa } from '../api.js'
import { CreateForm, RecordDetail, STATUS_BADGE } from './practicumShared.jsx'

/* درس‌پروژه و تحقیق و ارائه — کارآموزی صفحهٔ جداگانهٔ خودش را دارد (/internship) */
export default function Practicum() {
  const { user } = useAuth()
  const [meta, setMeta] = useState(null)
  const [records, setRecords] = useState([])
  const [openId, setOpenId] = useState(null)

  const isStudent = (user?.roles || []).includes('student')
  const isManager = (user?.roles || []).some(r => ['research_manager', 'system_admin'].includes(r))
  const load = () => {
    const path = isStudent ? '/practicum/mine' : isManager ? '/practicum/all' : '/practicum/supervised'
    api(path).then(rows => setRecords(rows.filter(r => r.course_type !== 'internship'))).catch(e => alert(e.message))
    api('/practicum/meta').then(setMeta).catch(() => {})
  }
  useEffect(() => { load() }, [])
  if (openId) return <RecordDetail id={openId} onBack={() => { setOpenId(null); load() }} user={user} />

  const allowed = (meta?.courses || []).filter(c => c.allowed && c.key !== 'internship')

  return (
    <>
      <div className="card">
        <h3>🛠️ درس‌پروژه و تحقیق و ارائه — نسبت به مقطع تحصیلی</h3>
        {meta?.my_degree ? (
          <div className="demo-banner">
            <b>🎓 مقطع شما: {meta.degree_fa}</b> — درس‌های مجاز شما:
            {allowed.map(c => <span key={c.key} className="badge teal" style={{ margin: '0 3px' }}>{c.fa}</span>)}
            {allowed.length === 0 && <span> برای مقطع شما درس عملی ثبت نمی‌شود؛ از فضای پژوهش و پروژه‌ها استفاده کنید.</span>}
          </div>
        ) : (
          <div className="error-box">مقطع تحصیلی در پروفایل شما ثبت نشده — از «پروفایل پژوهشی» مقطع را انتخاب کنید تا درس‌های مجاز نمایش داده شود.</div>
        )}
        <div className="hint" style={{ marginTop: 8 }}>
          چرخهٔ هر درس: <b>ارسال گزارش پیشرفت</b> ← <b>ارزیابی و بازخورد استاد مربوطه</b> ← <b>اصلاح در نوبت بعد</b> ← …
          تا تأیید نهایی با ثبت نمره. {meta?.round_guidance || 'معمولاً ۴ تا ۵ نوبت رفت‌وبرگشت لازم است.'}
          <br />
          💼 دنبال <b>کارآموزی</b> هستید؟ صفحهٔ جداگانهٔ «کارآموزی» در منو — با گزارش کار هفتگی/روزانه.
        </div>
      </div>

      {isStudent && <CreateForm meta={meta} onDone={load} title="➕ ثبت درس‌پروژه یا تحقیق و ارائه" />}
      {!isStudent && <div className="card"><h4>📥 درس‌های {isManager ? 'همهٔ دانشجویان' : 'تحت ارزیابی من'} ({toFa(records.length)})</h4></div>}

      <div className="grid cols-2">
        {records.map(r => (
          <div key={r.id} className="card">
            <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap' }}>
              <h4 style={{ margin: 0 }}>📘 {r.title}</h4>
              <span className={`badge ${STATUS_BADGE[r.status]}`}>{r.status_fa}</span>
            </div>
            <div className="hint" style={{ marginTop: 6 }}>
              {r.course_fa} · مقطع: {r.degree_fa} ·
              {isStudent ? ` استاد مربوطه: ${r.supervisor_name}` : ` دانشجو: ${r.student_name}`}
              {r.semester ? ` · ${r.semester}` : ''}
            </div>
            <div className="hint">نوبت‌های ارسال: {toFa(r.round_count)} {r.final_score != null && `· نمرهٔ نهایی: ${toFa(r.final_score)}`}</div>
            <div className="row" style={{ gap: 6, marginTop: 8 }}>
              <button className="btn small" onClick={() => setOpenId(r.id)}>نمایش چرخهٔ ارسال و بازخورد</button>
            </div>
          </div>
        ))}
        {records.length === 0 && (
          <div className="fancy-empty" style={{ gridColumn: '1 / -1' }}>
            <div className="big">🛠️</div>
            {isStudent
              ? 'هنوز درس‌پروژه یا تحقیق و ارائه ثبت نکرده‌اید — با فرم بالای صفحه ثبتش کنید.'
              : 'هنوز رکوردی برای ارزیابی دارید نیست.'}
          </div>
        )}
      </div>
    </>
  )
}
