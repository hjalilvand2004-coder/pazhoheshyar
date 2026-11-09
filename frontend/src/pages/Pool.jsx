import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, REQ_STATUS, STATUS_BADGE, fmtDateTime } from '../api.js'

export default function Pool() {
  const [items, setItems] = useState([])
  const [q, setQ] = useState('')
  const [field, setField] = useState('')
  const [skill, setSkill] = useState('')
  const [err, setErr] = useState('')

  const load = () => {
    const p = new URLSearchParams()
    if (q) p.set('q', q)
    if (field) p.set('field', field)
    if (skill) p.set('skill', skill)
    api(`/requests/pool?${p}`).then(setItems).catch(e => setErr(e.message))
  }
  useEffect(load, [q, field, skill])

  return (
    <>
      {err && <div className="error-box">{err}</div>}
      <div className="card">
        <h3>استخر پژوهشی</h3>
        <div className="hint">درخواست‌های منتشرشده دانشجویان که طبق دامنه‌بندی برای شما قابل مشاهده‌اند. با «اعلام آمادگی» وارد فرایند گفت‌وگو شوید.</div>
        <div className="row" style={{ marginTop: 10 }}>
          <input placeholder="جست‌وجو در عنوان و خلاصه…" value={q} onChange={e => setQ(e.target.value)} />
          <input placeholder="حوزه (مثال: هوش مصنوعی)" value={field} onChange={e => setField(e.target.value)} />
          <input placeholder="مهارت (مثال: پایتون)" value={skill} onChange={e => setSkill(e.target.value)} />
        </div>
      </div>
      {items.map(r => (
        <div className="card" key={r.id}>
          <div className="row">
            <b style={{ flex: 2 }}><Link to={`/requests/${r.id}`}>{r.title}</Link></b>
            <span className={`badge ${STATUS_BADGE[r.status]}`}>{REQ_STATUS[r.status]}</span>
            <span className="hint">دانشجو: {r.student_name}</span>
            <span className="hint">{fmtDateTime(r.updated_at)}</span>
          </div>
          <div style={{ fontSize: 13.5, marginTop: 4 }}>{r.summary || r.problem?.slice(0, 180)}</div>
          <div className="hint">حوزه: {r.field || '—'} {r.skills?.length ? `| مهارت‌ها: ${r.skills.join('، ')}` : ''} {r.timeline ? `| زمان: ${r.timeline}` : ''}</div>
          <Link className="btn small" style={{ marginTop: 8 }} to={`/requests/${r.id}`}>مشاهده و اعلام آمادگی</Link>
        </div>
      ))}
      {items.length === 0 && <div className="empty">درخواستی برای نمایش یافت نشد (فیلترها را تغییر دهید).</div>}
    </>
  )
}
