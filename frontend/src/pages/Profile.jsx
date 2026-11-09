import React, { useEffect, useState } from 'react'
import { useAuth } from '../auth.jsx'
import { api } from '../api.js'

const toList = (v) => (Array.isArray(v) ? v : (v || '').split('،').map(s => s.trim()).filter(Boolean))

export default function Profile() {
  const { user, hasRole } = useAuth()
  const [p, setP] = useState(null)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => { api('/profiles/me').then(setP).catch(e => setErr(e.message)) }, [])

  if (!p) return <div className="empty">در حال بارگذاری… {err && <div className="error-box">{err}</div>}</div>
  const isProfessor = hasRole('professor')
  const set = (k) => (e) => setP({ ...p, [k]: e.target.value })
  const setList = (k) => (e) => setP({ ...p, [k]: e.target.value })

  const save = async () => {
    setMsg(''); setErr('')
    try {
      const body = {
        field_of_study: p.field_of_study || '', faculty_name: p.faculty_name || '', degree: p.degree || '',
        interests: toList(p.interests), skills: toList(p.skills),
        bio: p.bio || '', research_history: p.research_history || '', publications: toList(p.publications),
        availability: p.availability || '', collaboration_type: p.collaboration_type || '',
        research_goal: p.research_goal || '', expertise: toList(p.expertise),
        methods_tools: p.methods_tools || '', capacity: Number(p.capacity) || 0, conditions: p.conditions || '',
      }
      const saved = await api('/profiles/me', { method: 'PUT', body })
      setP(saved)
      setMsg('پروفایل ذخیره شد.')
    } catch (e) { setErr(e.message) }
  }

  return (
    <>
      {msg && <div className="ok-box">{msg}</div>}
      {err && <div className="error-box">{err}</div>}
      <div className="card">
        <h3>پروفایل پژوهشی {isProfessor ? '(استاد)' : '(دانشجو)'}</h3>
        <div className="hint">
          {isProfessor
            ? 'حوزه‌های تخصصی، ظرفیت پذیرش و شرایط همکاری شما به دانشجویان نمایش داده می‌شود.'
            : 'اطلاعات حساس مثل سوابق کامل فقط برای خودتان و مدیران نمایش داده می‌شود؛ در نمای عمومی مخفی است.'}
        </div>
        <div className="grid cols-2">
          <div>
            <label className="fld">رشته</label>
            <input value={p.field_of_study || ''} onChange={set('field_of_study')} />
          </div>
          <div>
            <label className="fld">دانشکده (برای دامنه‌بندی دیده‌شدن درخواست‌ها)</label>
            <input value={p.faculty_name || ''} onChange={set('faculty_name')} />
          </div>
          <div>
            <label className="fld">مقطع</label>
            <input value={p.degree || ''} onChange={set('degree')} />
          </div>
          <div>
            <label className="fld">زمان آزاد / آمادگی</label>
            <input value={p.availability || ''} onChange={set('availability')} />
          </div>
        </div>
        <label className="fld">علایق پژوهشی (با ویرگول جدا کنید)</label>
        <input value={Array.isArray(p.interests) ? p.interests.join('، ') : (p.interests || '')} onChange={setList('interests')} />
        <label className="fld">مهارت‌ها (با ویرگول جدا کنید)</label>
        <input value={Array.isArray(p.skills) ? p.skills.join('، ') : (p.skills || '')} onChange={setList('skills')} />
        {!isProfessor && (
          <>
            <label className="fld">نوع همکاری مطلوب</label>
            <input value={p.collaboration_type || ''} onChange={set('collaboration_type')} />
            <label className="fld">هدف پژوهشی</label>
            <input value={p.research_goal || ''} onChange={set('research_goal')} />
            <label className="fld">سوابق پژوهشی (حساس — عمومی نمایش داده نمی‌شود)</label>
            <textarea rows={3} value={p.research_history || ''} onChange={set('research_history')} />
            <label className="fld">مقالات و نمونه‌کارها (حساس — با ویرگول)</label>
            <input value={Array.isArray(p.publications) ? p.publications.join('، ') : (p.publications || '')} onChange={setList('publications')} />
          </>
        )}
        {isProfessor && (
          <>
            <label className="fld">حوزه‌های تخصصی (با ویرگول)</label>
            <input value={Array.isArray(p.expertise) ? p.expertise.join('، ') : (p.expertise || '')} onChange={setList('expertise')} />
            <label className="fld">روش‌ها و ابزارهای مورد استفاده</label>
            <input value={p.methods_tools || ''} onChange={set('methods_tools')} />
            <div className="grid cols-2">
              <div>
                <label className="fld">ظرفیت پذیرش دانشجو (پروژه فعال همزمان)</label>
                <input type="number" min="0" value={p.capacity ?? 0} onChange={set('capacity')} />
              </div>
              <div>
                <label className="fld">شرایط همکاری</label>
                <input value={p.conditions || ''} onChange={set('conditions')} />
              </div>
            </div>
          </>
        )}
        <label className="fld">معرفی کوتاه</label>
        <textarea rows={3} value={p.bio || ''} onChange={set('bio')} />
        {p.academic_data && p.academic_data.source && (
          <div className="demo-banner">
            داده آموزشی دریافت‌شده از زیرساخت دانشجو۳۶۰ (نمونه آزمایشی): معدل {p.academic_data.gpa ?? '—'} —
            واحد گذرانده {p.academic_data.passed_credits ?? '—'} — فقط با دسترسی مجاز نمایش داده می‌شود.
          </div>
        )}
        <button className="btn" style={{ marginTop: 14 }} onClick={save}>ذخیره پروفایل</button>
      </div>
    </>
  )
}
