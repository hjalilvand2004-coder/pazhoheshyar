import React, { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useAuth } from '../auth.jsx'
import { api, uploadFile, fmtDateTime } from '../api.js'

export default function Chat() {
  const { requestId } = useParams()
  const { user } = useAuth()
  const [convs, setConvs] = useState([])
  const [active, setActive] = useState(null)
  const [messages, setMessages] = useState([])
  const [body, setBody] = useState('')
  const [agreement, setAgreement] = useState(null)
  const [err, setErr] = useState('')
  const boxRef = useRef(null)

  const loadConvs = () => api('/conversations/mine').then(c => {
    setConvs(c)
    if (!active && c.length) {
      const target = requestId ? c.find(x => String(x.request_id) === String(requestId)) : c[0]
      setActive(target || c[0])
    }
  }).catch(e => setErr(e.message))

  useEffect(() => { loadConvs() }, [requestId])

  const loadThread = () => {
    if (!active) return
    api(`/conversations/${active.id}/messages`).then(setMessages).catch(() => {})
    api(`/agreements/by-request/${active.request_id}`).then(a => setAgreement(a || null)).catch(() => setAgreement(null))
  }
  useEffect(() => { loadThread(); const t = setInterval(loadThread, 4000); return () => clearInterval(t) }, [active?.id])

  useEffect(() => { if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight }, [messages.length])

  const send = async (kind = 'text', attachmentId = null, textOverride = null) => {
    const text = textOverride ?? body
    if (!text && kind !== 'file') return
    try {
      await api(`/conversations/${active.id}/messages`, { method: 'POST', body: { body: text, kind, attachment_id: attachmentId } })
      setBody('')
      loadThread()
    } catch (e) { setErr(e.message) }
  }
  const sendFile = async (file) => {
    try {
      const up = await uploadFile(`/files/upload?conversation_id=${active.id}`, file)
      await api(`/conversations/${active.id}/messages`, { method: 'POST', body: { body: up.orig_name, kind: 'file', attachment_id: up.id } })
      loadThread()
    } catch (e) { setErr(e.message) }
  }
  const report = async () => {
    const reason = window.prompt('دلیل گزارش مزاحمت یا سوءاستفاده؟')
    if (!reason) return
    try { const r = await api(`/conversations/${active.id}/report`, { method: 'POST', body: { reason } }); alert(r.message) }
    catch (e) { setErr(e.message) }
  }
  const sign = async () => {
    setErr('')
    try {
      const r = await api(`/agreements/${agreement.id}/sign`, { method: 'POST' })
      if (r.project_id) { window.location.assign(`/projects/${r.project_id}`); return }
      alert(r.message || 'ثبت شد'); loadThread()
    } catch (e) { setErr(e.message) }
  }

  return (
    <div className="grid" style={{ gridTemplateColumns: '280px 1fr' }}>
      <div className="card" style={{ maxHeight: 560, overflowY: 'auto' }}>
        <h3>گفت‌وگوها</h3>
        {convs.length === 0 && <div className="empty">گفت‌وگویی ندارید. از صفحه درخواست، «گفت‌وگو» را آغاز کنید.</div>}
        {convs.map(c => (
          <div key={c.id} onClick={() => setActive(c)}
               style={{ padding: 10, borderRadius: 9, cursor: 'pointer', marginBottom: 6, background: active?.id === c.id ? 'var(--primary-light)' : '#f8fafc' }}>
            <b>{c.request_title}</b>
            <div className="hint">{user.id === c.professor_id ? `دانشجو: ${c.student_name}` : `استاد: ${c.professor_name}`}</div>
          </div>
        ))}
      </div>
      <div className="card">
        {err && <div className="error-box">{err}</div>}
        {!active && <div className="empty">یک گفت‌وگو انتخاب کنید.</div>}
        {active && (
          <>
            <h3>💬 {active.request_title}</h3>
            <div className="hint">طرف مقابل: {user.id === active.professor_id ? active.student_name : active.professor_name}</div>
            {agreement && (
              <div className="card" style={{ background: '#f0fdfa', margin: '10px 0' }}>
                <h3>📜 توافق‌نامه همکاری {agreement.fully_signed ? <span className="badge green">امضاشده دوطرفه</span> : <span className="badge amber">در انتظار امضا</span>}</h3>
                <div style={{ fontSize: 13 }}>
                  <b>مسئولیت‌ها:</b> <div className="hint" style={{ whiteSpace: 'pre-wrap' }}>{agreement.responsibilities}</div>
                  <b>زمان‌بندی:</b> <span className="hint">{agreement.timeline}</span><br />
                  <b>خروجی‌ها:</b> <span className="hint">{agreement.deliverables}</span><br />
                  <b>محرمانگی:</b> <span className="hint">{agreement.confidentiality}</span><br />
                  <b>مالکیت فکری:</b> <span className="hint">{agreement.ip_ownership}</span>
                </div>
                {!agreement.fully_signed && (
                  <button className="btn" style={{ marginTop: 8 }} onClick={sign}>
                    ✍️ امضای توافق‌نامه {user.id === active.student_id ? '(دانشجو)' : '(استاد)'}
                  </button>
                )}
              </div>
            )}
            <div className="chat-box" ref={boxRef}>
              {messages.map(m => (
                <div key={m.id} className={`msg ${m.sender_id === user.id ? 'me' : ''}`}>
                  {m.kind === 'meeting' && <b>📅 درخواست جلسه: </b>}
                  {m.kind === 'meeting_result' && <b>📋 نتیجه جلسه: </b>}
                  {m.kind === 'file' && <b>📎 فایل: </b>}
                  {m.body}
                  <div className="meta">{m.sender_name} — {fmtDateTime(m.created_at)}</div>
                </div>
              ))}
              {messages.length === 0 && <div className="empty">اولین پیام را بفرستید.</div>}
            </div>
            <div className="row" style={{ marginTop: 10 }}>
              <input placeholder="پیام…" value={body} onChange={e => setBody(e.target.value)}
                     onKeyDown={e => e.key === 'Enter' && send()} />
              <button className="btn" style={{ flex: 0 }} onClick={() => send()}>ارسال</button>
              <button className="btn secondary" style={{ flex: 0 }} onClick={() => {
                const when = window.prompt('زمان پیشنهادی جلسه (مثال: شنبه ۱۰ صبح):')
                if (when) send('meeting', null, when)
              }}>📅 جلسه</button>
              <label className="btn secondary" style={{ flex: 0, cursor: 'pointer' }}>
                📎 فایل
                <input type="file" style={{ display: 'none' }} onChange={e => e.target.files?.[0] && sendFile(e.target.files[0])} />
              </label>
              <button className="btn danger" style={{ flex: 0 }} onClick={report}>🚩 گزارش</button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
