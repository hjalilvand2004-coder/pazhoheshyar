import React, { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth.jsx'
import { api, SCOPE_LABEL } from '../api.js'

export default function RequestForm() {
  const nav = useNavigate()
  const [params] = useSearchParams()
  const { hasRole } = useAuth()
  const [form, setForm] = useState({
    title: '', summary: '', problem: '', goals: '', field: '', skills: [], timeline: '',
    scope: 'all', faculty_name: '', selected_professors: [], secret_details: '',
    university_approval_required: false,
  })
  const [profs, setProfs] = useState([])
  const [files, setFiles] = useState([])
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const topicId = params.get('topic')
    if (topicId) {
      api(`/topics/${topicId}`).then(t => setForm(f => ({
        ...f, title: t.kind === 'template' ? '' : t.title,
        problem: t.problem_statement || '', goals: t.expected_output || '',
        field: t.field || '', skills: t.required_skills || [], timeline: t.estimated_duration || '', topic_id: t.id,
      }))).catch(() => {})
    }
    api('/profiles/professors').then(setProfs).catch(() => {})
  }, [])

  if (!hasRole('student')) return <div className="empty">فقط دانشجویان می‌توانند درخواست ثبت کنند.</div>
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })

  const submit = async (publish) => {
    setErr(''); setBusy(true)
    try {
      const body = {
        ...form,
        skills: typeof form.skills === 'string' ? form.skills.split('،').map(s => s.trim()).filter(Boolean) : (form.skills || []),
        selected_professors: form.scope === 'selected' ? form.selected_professors.map(Number) : [],
      }
      if (body.scope === 'selected' && body.selected_professors.length === 0) {
        throw new Error('حداقل یک استاد منتخب انتخاب کنید')
      }
      const r = await api(`/requests?publish_now=${publish}`, { method: 'POST', body })
      nav(`/requests/${r.id}`)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <>
      {err && <div className="error-box">{err}</div>}
      <div className="card">
        <h3>فرم ثبت درخواست پژوهش</h3>
        <div className="hint">
          درخواست شما وارد «استخر پژوهشی» می‌شود؛ اساتید واجد شرایط آن را می‌بینند و اعلام آمادگی می‌کنند.
          اعلام آمادگی به‌تنهایی اتصال قطعی نیست؛ اتصال با تأیید دوطرفه و در صورت نیاز تأیید دانشگاه انجام می‌شود.
        </div>
        <label className="fld">عنوان *</label>
        <input value={form.title} onChange={set('title')} placeholder="مثال: دستیار هوشمند پاسخ به پرسش‌های دانشجویی" />
        <div className="grid cols-2">
          <div>
            <label className="fld">حوزه علمی</label>
            <input value={form.field} onChange={set('field')} />
          </div>
          <div>
            <label className="fld">زمان‌بندی پیشنهادی</label>
            <input value={form.timeline} onChange={set('timeline')} placeholder="مثال: ۴ ماه توسعه + ۲ ماه ارزیابی" />
          </div>
        </div>
        <label className="fld">شرح مسئله *</label>
        <textarea rows={3} value={form.problem} onChange={set('problem')} />
        <label className="fld">اهداف و خروجی مورد انتظار</label>
        <textarea rows={2} value={form.goals} onChange={set('goals')} />
        <label className="fld">مهارت‌های لازم (با ویرگول)</label>
        <input value={Array.isArray(form.skills) ? form.skills.join('، ') : (form.skills || '')}
               onChange={e => setForm({ ...form, skills: e.target.value })} />
        <label className="fld">خلاصه قابل نمایش (برای ایده محرمانه — این بخش در استخر دیده می‌شود)</label>
        <textarea rows={2} value={form.summary} onChange={set('summary')} />
        <label className="fld">جزئیات محرمانه (فقط با اجازه شما به استاد منتخب نمایش داده می‌شود)</label>
        <textarea rows={2} value={form.secret_details} onChange={set('secret_details')} />
        <div className="grid cols-2">
          <div>
            <label className="fld">دامنه دیده‌شدن درخواست</label>
            <select value={form.scope} onChange={set('scope')}>
              <option value="all">{SCOPE_LABEL.all}</option>
              <option value="faculty">{SCOPE_LABEL.faculty}</option>
              <option value="selected">{SCOPE_LABEL.selected}</option>
            </select>
          </div>
          {form.scope === 'faculty' && (
            <div>
              <label className="fld">نام دانشکده *</label>
              <input value={form.faculty_name} onChange={set('faculty_name')} />
            </div>
          )}
        </div>
        {form.scope === 'selected' && (
          <>
            <label className="fld">اساتید منتخب *</label>
            <div style={{ maxHeight: 180, overflowY: 'auto', border: '1px solid var(--border)', borderRadius: 9, padding: 8 }}>
              {profs.map(pr => (
                <label key={pr.user_id} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '4px 2px' }}>
                  <input type="checkbox" style={{ width: 'auto' }}
                         checked={form.selected_professors.includes(pr.user_id)}
                         onChange={e => setForm(f => ({
                           ...f,
                           selected_professors: e.target.checked
                             ? [...f.selected_professors, pr.user_id]
                             : f.selected_professors.filter(id => id !== pr.user_id),
                         }))} />
                  {pr.display_name} — {(pr.expertise || []).join('، ')}
                </label>
              ))}
              {profs.length === 0 && <div className="hint">استادی یافت نشد.</div>}
            </div>
          </>
        )}
        <label style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 12 }}>
          <input type="checkbox" style={{ width: 'auto' }} checked={form.university_approval_required} onChange={set('university_approval_required')} />
          این همکاری نیازمند تأیید دانشگاه (مدیر پژوهش) است
        </label>
        <div className="row" style={{ marginTop: 16 }}>
          <button className="btn" onClick={() => submit(true)} disabled={busy || !form.title || !form.problem}>
            🚀 ثبت و انتشار در استخر
          </button>
          <button className="btn secondary" onClick={() => submit(false)} disabled={busy || !form.title}>ذخیره پیش‌نویس</button>
        </div>
      </div>
    </>
  )
}
