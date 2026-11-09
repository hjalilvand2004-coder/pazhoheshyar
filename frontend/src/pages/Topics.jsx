import React, { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth.jsx'
import { api } from '../api.js'

const EMPTY = {
  kind: 'topic', title: '', field: '', problem_statement: '', research_questions: '', expected_output: '',
  suggested_method: '', required_skills: [], required_data_equipment: '', estimated_duration: '',
  team_size: 1, acceptance_terms: '', funding_status: '', ethics_requirements: '',
}

export default function Topics() {
  const { hasRole } = useAuth()
  const nav = useNavigate()
  const [items, setItems] = useState([])
  const [q, setQ] = useState('')
  const [kind, setKind] = useState('')
  const [editing, setEditing] = useState(null)
  const [err, setErr] = useState('')

  const load = () => {
    const params = new URLSearchParams()
    if (q) params.set('q', q)
    if (kind) params.set('kind', kind)
    api(`/topics?${params}`).then(setItems).catch(e => setErr(e.message))
  }
  useEffect(load, [q, kind])

  const canPublish = hasRole('professor', 'research_manager')

  const save = async () => {
    setErr('')
    try {
      const body = { ...editing, required_skills: typeof editing.required_skills === 'string'
        ? editing.required_skills.split('،').map(s => s.trim()).filter(Boolean) : editing.required_skills }
      if (editing.id) await api(`/topics/${editing.id}`, { method: 'PUT', body })
      else await api('/topics', { method: 'POST', body })
      setEditing(null); load()
    } catch (e) { setErr(e.message) }
  }

  const remove = async (id) => {
    if (!window.confirm('این موضوع غیرفعال شود؟')) return
    await api(`/topics/${id}`, { method: 'DELETE' }).catch(e => setErr(e.message))
    load()
  }

  return (
    <>
      {err && <div className="error-box">{err}</div>}
      <div className="card">
        <h3>بانک موضوعات و الگوهای استاندارد</h3>
        <div className="row">
          <input placeholder="جست‌وجو در عنوان و شرح…" value={q} onChange={e => setQ(e.target.value)} />
          <select value={kind} onChange={e => setKind(e.target.value)} style={{ maxWidth: 200 }}>
            <option value="">همه</option>
            <option value="topic">موضوع پژوهشی</option>
            <option value="template">الگوی استاندارد</option>
          </select>
          {canPublish && <button className="btn" onClick={() => setEditing({ ...EMPTY })}>➕ انتشار موضوع/الگو</button>}
        </div>
      </div>

      {editing && (
        <div className="card">
          <h3>{editing.id ? 'ویرایش' : 'انتشار'} {editing.kind === 'template' ? 'الگوی استاندارد' : 'موضوع پژوهشی'}</h3>
          <div className="grid cols-2">
            <div>
              <label className="fld">نوع</label>
              <select value={editing.kind} onChange={e => setEditing({ ...editing, kind: e.target.value })}>
                <option value="topic">موضوع پژوهشی</option>
                <option value="template">الگوی استاندارد تعریف موضوع</option>
              </select>
            </div>
            <div>
              <label className="fld">حوزه علمی</label>
              <input value={editing.field} onChange={e => setEditing({ ...editing, field: e.target.value })} />
            </div>
          </div>
          <label className="fld">عنوان *</label>
          <input value={editing.title} onChange={e => setEditing({ ...editing, title: e.target.value })} />
          <label className="fld">شرح مسئله</label>
          <textarea rows={2} value={editing.problem_statement} onChange={e => setEditing({ ...editing, problem_statement: e.target.value })} />
          <div className="grid cols-2">
            <div>
              <label className="fld">پرسش پژوهش</label>
              <textarea rows={2} value={editing.research_questions} onChange={e => setEditing({ ...editing, research_questions: e.target.value })} />
            </div>
            <div>
              <label className="fld">خروجی مورد انتظار</label>
              <textarea rows={2} value={editing.expected_output} onChange={e => setEditing({ ...editing, expected_output: e.target.value })} />
            </div>
          </div>
          <label className="fld">روش پیشنهادی</label>
          <input value={editing.suggested_method} onChange={e => setEditing({ ...editing, suggested_method: e.target.value })} />
          <div className="grid cols-3">
            <div>
              <label className="fld">مهارت‌های لازم (با ویرگول)</label>
              <input value={Array.isArray(editing.required_skills) ? editing.required_skills.join('، ') : editing.required_skills || ''}
                     onChange={e => setEditing({ ...editing, required_skills: e.target.value })} />
            </div>
            <div>
              <label className="fld">زمان تقریبی</label>
              <input value={editing.estimated_duration} onChange={e => setEditing({ ...editing, estimated_duration: e.target.value })} />
            </div>
            <div>
              <label className="fld">تعداد اعضا</label>
              <input type="number" min="1" value={editing.team_size} onChange={e => setEditing({ ...editing, team_size: e.target.value })} />
            </div>
          </div>
          <div className="grid cols-3">
            <div>
              <label className="fld">داده‌ها/تجهیزات لازم</label>
              <input value={editing.required_data_equipment} onChange={e => setEditing({ ...editing, required_data_equipment: e.target.value })} />
            </div>
            <div>
              <label className="fld">وضعیت تأمین مالی</label>
              <input value={editing.funding_status} onChange={e => setEditing({ ...editing, funding_status: e.target.value })} />
            </div>
            <div>
              <label className="fld">الزامات اخلاق پژوهش</label>
              <input value={editing.ethics_requirements} onChange={e => setEditing({ ...editing, ethics_requirements: e.target.value })} />
            </div>
          </div>
          <label className="fld">شرایط پذیرش</label>
          <input value={editing.acceptance_terms} onChange={e => setEditing({ ...editing, acceptance_terms: e.target.value })} />
          <div className="row" style={{ marginTop: 12 }}>
            <button className="btn" onClick={save} disabled={!editing.title}>ذخیره</button>
            <button className="btn ghost" onClick={() => setEditing(null)}>انصراف</button>
          </div>
        </div>
      )}

      <div className="grid cols-2">
        {items.map(t => (
          <div className="card" key={t.id}>
            <h3>
              <span className={`badge ${t.kind === 'template' ? 'teal' : ''}`}>{t.kind === 'template' ? 'الگو' : 'موضوع'}</span>
              {t.title}
            </h3>
            <div className="hint">حوزه: {t.field || '—'} | استاد: {t.owner_name} | زمان: {t.estimated_duration || '—'} | ظرفیت تیم: {t.team_size}</div>
            {t.problem_statement && <div style={{ fontSize: 13.5 }}>{t.problem_statement}</div>}
            {t.required_skills?.length > 0 && <div className="hint">مهارت‌های لازم: {t.required_skills.join('، ')}</div>}
            {t.acceptance_terms && <div className="hint">شرایط پذیرش: {t.acceptance_terms}</div>}
            <div className="row" style={{ marginTop: 10 }}>
              {hasRole('student') && (
                <button className="btn small" onClick={() => nav(`/requests/new?topic=${t.id}`)}>
                  {t.kind === 'template' ? 'بر اساس این الگو درخواست بده' : 'انتخاب این موضوع'}
                </button>
              )}
              {(hasRole('professor', 'research_manager')) && (
                <>
                  <button className="btn small secondary" onClick={() => setEditing({ ...t, required_skills: t.required_skills?.join('، ') })}>ویرایش</button>
                  <button className="btn small danger" onClick={() => remove(t.id)}>حذف</button>
                </>
              )}
            </div>
          </div>
        ))}
      </div>
      {items.length === 0 && <div className="empty">موردی یافت نشد.</div>}
    </>
  )
}
