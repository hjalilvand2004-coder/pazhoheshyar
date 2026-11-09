import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fmtDateTime } from '../api.js'

export default function Projects() {
  const [items, setItems] = useState([])
  const [err, setErr] = useState('')
  useEffect(() => { api('/projects/mine').then(setItems).catch(e => setErr(e.message)) }, [])

  return (
    <>
      {err && <div className="error-box">{err}</div>}
      <div className="card">
        <h3>پروژه‌های من</h3>
        <div className="hint">پروژه فقط پس از توافق دوطرفه (و در صورت نیاز تأیید دانشگاه) تشکیل می‌شود.</div>
      </div>
      {items.map(p => (
        <div className="card" key={p.id}>
          <div className="row">
            <b style={{ flex: 2 }}><Link to={`/projects/${p.id}`}>{p.title}</Link></b>
            <span className={`badge ${p.status === 'active' ? 'green' : 'gray'}`}>
              {p.status === 'active' ? 'فعال' : p.status === 'closing' ? 'در حال خاتمه' : 'خاتمه‌یافته'}
            </span>
            <span className="hint">مسئول: {p.lead_professor_name}</span>
            <span className="hint">{fmtDateTime(p.created_at)}</span>
          </div>
          <div className="hint">
            اعضا: {p.members?.map(m => `${m.name || 'کاربر #' + m.user_id} (${m.role === 'lead' ? 'مسئول' : m.role === 'student' ? 'دانشجو' : m.role === 'advisor' ? 'استاد مشاور' : 'عضو'})`).join('، ')}
          </div>
        </div>
      ))}
      {items.length === 0 && <div className="empty">پروژه‌ای ندارید.</div>}
    </>
  )
}
