import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth.jsx'
import { api, fmtDateTime, REQ_STATUS } from '../api.js'

export default function Admin() {
  const { hasRole } = useAuth()
  const [metrics, setMetrics] = useState(null)
  const [events, setEvents] = useState([])
  const [users, setUsers] = useState([])
  const [err, setErr] = useState('')

  const load = () => {
    api('/admin/metrics').then(setMetrics).catch(e => setErr(e.message))
    api('/events?limit=60').then(setEvents).catch(() => {})
    api('/admin/users').then(setUsers).catch(() => {})
  }
  useEffect(load, [])

  const isSysAdmin = hasRole('system_admin')
  const ROLE_LABELS = { student: 'دانشجو', professor: 'استاد', research_manager: 'مدیر پژوهش', system_admin: 'مدیر سامانه' }
  const setRole = async (uid, role) => {
    const u = users.find(x => x.id === uid)
    const roles = u.roles.includes(role) ? u.roles.filter(r => r !== role) : [...u.roles, role]
    try { await api(`/admin/users/${uid}/roles`, { method: 'PATCH', body: { roles } }); load() }
    catch (e) { setErr(e.message) }
  }

  const maxCount = metrics ? Math.max(1, ...Object.values(metrics.requests_by_status || {})) : 1

  return (
    <>
      {err && <div className="error-box">{err}</div>}
      {metrics && (
        <div className="grid cols-4">
          <div className="stat"><div className="num">{metrics.requests_total}</div><div className="lbl">کل درخواست‌ها</div></div>
          <div className="stat"><div className="num">{metrics.offers_total}</div><div className="lbl">اعلام آمادگی</div></div>
          <div className="stat"><div className="num">{metrics.projects_active}</div><div className="lbl">پروژه فعال</div></div>
          <div className="stat"><div className="num">{metrics.users_total}</div><div className="lbl">کاربران ({metrics.students} دانشجو / {metrics.professors} استاد)</div></div>
        </div>
      )}

      {metrics && (
        <div className="card">
          <h3>درخواست‌ها به تفکیک وضعیت</h3>
          {Object.entries(metrics.requests_by_status || {}).map(([s, c]) => (
            <div key={s} style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '6px 0' }}>
              <span style={{ width: 170, fontSize: 13 }}>{REQ_STATUS[s]}</span>
              <div style={{ flex: 1, height: 14, background: '#e2e8f0', borderRadius: 999, overflow: 'hidden' }}>
                <div style={{ width: `${(c / maxCount) * 100}%`, height: '100%', background: 'var(--primary)' }} />
              </div>
              <b style={{ width: 30 }}>{c}</b>
            </div>
          ))}
        </div>
      )}

      <div className="card">
        <h3>🧾 جریان رخدادها (۶۰ رویداد اخیر)</h3>
        <div className="hint">این جریان با <code>X-Service-Token</code> در دسترس سایر سامانه‌های اکوسیستم دانشجو۳۶۰ نیز هست.</div>
        <table className="tbl">
          <thead><tr><th>رخداد</th><th>کاربر</th><th>جزئیات</th><th>زمان</th></tr></thead>
          <tbody>
            {events.map(e => (
              <tr key={e.id}>
                <td><span className="badge">{e.type}</span></td>
                <td>{e.actor_id ? '#' + e.actor_id : '—'}</td>
                <td className="hint" style={{ direction: 'ltr', textAlign: 'left' }}>{JSON.stringify(e.payload).slice(0, 90)}</td>
                <td className="hint">{fmtDateTime(e.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>👥 کاربران {isSysAdmin && '(مدیر سامانه: نقش‌ها قابل ویرایش است)'}</h3>
        <table className="tbl">
          <thead><tr><th>نام</th><th>نام کاربری</th><th>نقش‌ها</th><th>SSO</th></tr></thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id}>
                <td>{u.display_name}</td>
                <td dir="ltr" style={{ textAlign: 'left' }}>{u.username}</td>
                <td>
                  <div className="row" style={{ gap: 6 }}>
                    {u.role_labels?.map(r => <span key={r} className="badge teal">{r}</span>)}
                    {isSysAdmin && ['student', 'professor', 'research_manager', 'system_admin'].map(r => (
                      <button key={r} className="btn ghost small" style={{ minHeight: 24, padding: '0 8px', fontSize: 11 }}
                              onClick={() => setRole(u.id, r)} title={`تغییر نقش ${ROLE_LABELS[r]}`}>
                        {u.roles.includes(r) ? `− ${ROLE_LABELS[r]}` : `+ ${ROLE_LABELS[r]}`}
                      </button>
                    ))}
                  </div>
                </td>
                <td>{u.sso_linked ? '🔗' : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
