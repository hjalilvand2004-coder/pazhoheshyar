import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useAuth } from '../auth.jsx'
import { api, uploadFile, fmtDateTime } from '../api.js'

const TASK_STATUS = { todo: 'در انتظار', doing: 'در حال انجام', done: 'انجام‌شده' }

export default function ProjectDetail() {
  const { id } = useParams()
  const { user, hasRole } = useAuth()
  const [p, setP] = useState(null)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [tab, setTab] = useState('tasks')
  const [newTask, setNewTask] = useState({ title: '', description: '', due_date: '' })
  const [newMember, setNewMember] = useState({ username: '', role: 'member' })
  const [newMeeting, setNewMeeting] = useState({ title: '', scheduled_at: '' })
  const [newReport, setNewReport] = useState({ percent: 0, note: '' })
  const [feedback, setFeedback] = useState({})

  const load = () => api(`/projects/${id}`).then(setP).catch(e => setErr(e.message))
  useEffect(load, [id])

  if (err && !p) return <div className="error-box">{err}</div>
  if (!p) return <div className="empty">در حال بارگذاری…</div>

  const me = p.members.find(m => m.user_id === user.id)
  const isLead = me?.role === 'lead'
  const isManager = hasRole('research_manager', 'system_admin')
  const run = async (fn, okMsg) => {
    setErr(''); setMsg('')
    try { await fn(); if (okMsg) setMsg(okMsg); load() } catch (e) { setErr(e.message) }
  }

  return (
    <>
      {err && <div className="error-box">{err}</div>}
      {msg && <div className="ok-box">{msg}</div>}
      <div className="card">
        <div className="row">
          <h3 style={{ flex: 2, margin: 0 }}>🚀 {p.title}</h3>
          <span className={`badge ${p.status === 'active' ? 'green' : 'gray'}`}>
            {p.status === 'active' ? 'فعال' : p.status === 'closing' ? 'در حال خاتمه' : 'خاتمه‌یافته'}
          </span>
        </div>
        <div className="hint">مسئول پروژه: {p.lead_professor_name} | تشکیل: {fmtDateTime(p.created_at)}</div>
        <div style={{ marginTop: 10 }}>
          <div className="hint">آخرین پیشرفت: {p.percent ?? 0}٪</div>
          <div className="progress-bar"><div style={{ width: `${p.percent ?? 0}%` }} /></div>
        </div>
        <div className="row" style={{ marginTop: 10 }}>
          {p.members.map(m => <span key={m.user_id} className="badge teal">{m.name || 'عضو'} — {m.role === 'lead' ? 'مسئول' : m.role === 'student' ? 'دانشجو' : m.role === 'advisor' ? 'استاد مشاور' : 'عضو'}</span>)}
        </div>
        {(isLead || isManager) && p.status === 'active' && (
          <button className="btn danger small" style={{ marginTop: 10 }}
                  onClick={() => run(() => api(`/projects/${id}/close?reason=خاتمه`, { method: 'POST' }), 'پروژه خاتمه یافت')}>
            خاتمه پروژه
          </button>
        )}
      </div>

      <div className="row" style={{ marginBottom: 12 }}>
        {[['tasks', 'وظایف'], ['members', 'اعضا'], ['meetings', 'جلسات'], ['files', 'فایل‌ها'], ['progress', 'پیشرفت و بازخورد']].map(([k, lbl]) => (
          <button key={k} className={`btn small ${tab === k ? '' : 'ghost'}`} onClick={() => setTab(k)}>{lbl}</button>
        ))}
      </div>

      {tab === 'tasks' && (
        <div className="card">
          <h3>وظایف</h3>
          <table className="tbl">
            <thead><tr><th>عنوان</th><th>شرح</th><th>مهلت</th><th>وضعیت</th><th></th></tr></thead>
            <tbody>
              {p.tasks.map(t => (
                <tr key={t.id}>
                  <td><b>{t.title}</b></td>
                  <td className="hint">{t.description}</td>
                  <td className="hint">{t.due_date || '—'}</td>
                  <td><span className={`badge ${t.status === 'done' ? 'green' : t.status === 'doing' ? 'amber' : ''}`}>{TASK_STATUS[t.status]}</span></td>
                  <td>
                    {t.status !== 'done' && (
                      <button className="btn small secondary"
                              onClick={() => run(() => api(`/projects/${id}/tasks/${t.id}`, { method: 'PATCH', body: { status: t.status === 'todo' ? 'doing' : 'done' } }))}>
                        {t.status === 'todo' ? 'شروع' : 'تکمیل'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {p.tasks.length === 0 && <tr><td colSpan={5} className="empty">وظیفه‌ای ثبت نشده است.</td></tr>}
            </tbody>
          </table>
          {(me || isManager) && (
            <div className="row" style={{ marginTop: 12 }}>
              <input placeholder="عنوان وظیفه" value={newTask.title} onChange={e => setNewTask({ ...newTask, title: e.target.value })} />
              <input placeholder="مهلت (YYYY-MM-DD)" value={newTask.due_date} onChange={e => setNewTask({ ...newTask, due_date: e.target.value })} style={{ maxWidth: 180 }} />
              <button className="btn" style={{ flex: 0 }} disabled={!newTask.title}
                      onClick={() => run(async () => { await api(`/projects/${id}/tasks`, { method: 'POST', body: { ...newTask, due_date: newTask.due_date || null } }); setNewTask({ title: '', description: '', due_date: '' }) })}>
                افزودن وظیفه
              </button>
            </div>
          )}
        </div>
      )}

      {tab === 'members' && (
        <div className="card">
          <h3>اعضای پروژه</h3>
          <table className="tbl">
            <tbody>
              {p.members.map(m => (
                <tr key={m.user_id}><td>{m.name || 'کاربر #' + m.user_id}</td><td><span className="badge">{m.role}</span></td></tr>
              ))}
            </tbody>
          </table>
          {(isLead || isManager) && (
            <div className="row" style={{ marginTop: 12 }}>
              <input placeholder="نام کاربری عضو جدید" value={newMember.username} onChange={e => setNewMember({ ...newMember, username: e.target.value })} dir="ltr" style={{ textAlign: 'left' }} />
              <select value={newMember.role} onChange={e => setNewMember({ ...newMember, role: e.target.value })} style={{ maxWidth: 180 }}>
                <option value="advisor">استاد مشاور</option>
                <option value="member">عضو</option>
                <option value="student">دانشجو</option>
              </select>
              <button className="btn" style={{ flex: 0 }} disabled={!newMember.username}
                      onClick={() => run(() => api(`/projects/${id}/members`, { method: 'POST', body: newMember }), 'عضو اضافه شد')}>
                افزودن (با تأیید مسئول)
              </button>
            </div>
          )}
        </div>
      )}

      {tab === 'meetings' && (
        <div className="card">
          <h3>تقویم جلسات و صورت‌جلسه</h3>
          {p.meetings.map(m => (
            <div key={m.id} className="card" style={{ background: '#f8fafc' }}>
              <b>{m.title}</b> <span className="hint">{fmtDateTime(m.scheduled_at)}</span>
              {m.minutes ? <div className="hint" style={{ whiteSpace: 'pre-wrap' }}>صورت‌جلسه: {m.minutes}</div> : (
                (me || isManager) && (
                  <div className="row" style={{ marginTop: 6 }}>
                    <input placeholder="متن صورت‌جلسه…" onChange={e => setFeedback({ ...feedback, [`m${m.id}`]: e.target.value })} />
                    <button className="btn small" style={{ flex: 0 }}
                            onClick={() => run(() => api(`/projects/${id}/meetings/${m.id}`, { method: 'PATCH', body: { minutes: feedback[`m${m.id}`] || '' } }), 'ثبت شد')}>
                      ثبت صورت‌جلسه
                    </button>
                  </div>
                )
              )}
            </div>
          ))}
          {p.meetings.length === 0 && <div className="empty">جلسه‌ای ثبت نشده است.</div>}
          {(me || isManager) && (
            <div className="row" style={{ marginTop: 10 }}>
              <input placeholder="عنوان جلسه" value={newMeeting.title} onChange={e => setNewMeeting({ ...newMeeting, title: e.target.value })} />
              <input placeholder="زمان (ISO مثل 2026-01-10T10:00)" value={newMeeting.scheduled_at} onChange={e => setNewMeeting({ ...newMeeting, scheduled_at: e.target.value })} />
              <button className="btn" style={{ flex: 0 }} disabled={!newMeeting.title}
                      onClick={() => run(async () => { await api(`/projects/${id}/meetings`, { method: 'POST', body: newMeeting }); setNewMeeting({ title: '', scheduled_at: '' }) })}>
                ثبت جلسه
              </button>
            </div>
          )}
        </div>
      )}

      {tab === 'files' && (
        <div className="card">
          <h3>فایل‌ها و نسخه‌های مستندات</h3>
          {p.files.map(f => (
            <div key={f.id} className="row" style={{ borderBottom: '1px solid var(--border)', padding: '6px 0' }}>
              <span style={{ flex: 2 }}>📄 {f.orig_name}</span>
              <span className="hint">{Math.round(f.size / 1024)} KB</span>
              <a className="btn small secondary" href={`/api/v1/files/${f.id}`}>دانلود</a>
            </div>
          ))}
          {p.files.length === 0 && <div className="empty">فایلی نیست.</div>}
          {(me || isManager) && (
            <div style={{ marginTop: 10 }}>
              <label className="btn secondary" style={{ cursor: 'pointer' }}>
                📤 بارگذاری فایل
                <input type="file" style={{ display: 'none' }} onChange={e => e.target.files?.[0] && run(() => uploadFile(`/projects/${id}/files`, e.target.files[0]), 'فایل بارگذاری شد')} />
              </label>
            </div>
          )}
        </div>
      )}

      {tab === 'progress' && (
        <div className="card">
          <h3>گزارش پیشرفت و بازخورد استاد</h3>
          {p.reports.map(r => (
            <div key={r.id} className="card" style={{ background: '#f8fafc' }}>
              <b>{r.author_name}</b> — پیشرفت {r.percent}٪ <span className="hint">{fmtDateTime(r.created_at)}</span>
              <div>{r.note}</div>
              {r.feedback && <div className="ok-box">بازخورد استاد: {r.feedback}</div>}
              {isLead && !r.feedback && (
                <div className="row" style={{ marginTop: 6 }}>
                  <input placeholder="بازخورد شما…" onChange={e => setFeedback({ ...feedback, [`r${r.id}`]: e.target.value })} />
                  <button className="btn small" style={{ flex: 0 }}
                          onClick={() => run(() => api(`/projects/${id}/progress/${r.id}`, { method: 'PATCH', body: { feedback: feedback[`r${r.id}`] || '' } }), 'بازخورد ثبت شد')}>
                    ثبت بازخورد
                  </button>
                </div>
              )}
            </div>
          ))}
          {p.reports.length === 0 && <div className="empty">گزارشی ثبت نشده است.</div>}
          {me && (
            <div className="row" style={{ marginTop: 10 }}>
              <input type="number" min="0" max="100" value={newReport.percent} onChange={e => setNewReport({ ...newReport, percent: e.target.value })} style={{ maxWidth: 120 }} />
              <input placeholder="توضیح پیشرفت…" value={newReport.note} onChange={e => setNewReport({ ...newReport, note: e.target.value })} />
              <button className="btn" style={{ flex: 0 }} onClick={() => run(async () => { await api(`/projects/${id}/progress`, { method: 'POST', body: { percent: Number(newReport.percent), note: newReport.note } }); setNewReport({ percent: 0, note: '' }) })}>
                ثبت گزارش پیشرفت
              </button>
            </div>
          )}
        </div>
      )}
    </>
  )
}
