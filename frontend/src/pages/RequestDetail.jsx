import React, { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAuth } from '../auth.jsx'
import { api, uploadFile, REQ_STATUS, REQ_FLOW, OFFER_STATUS, STATUS_BADGE, SCOPE_LABEL, fmtDateTime } from '../api.js'

function Stepper({ status }) {
  const idx = REQ_FLOW.indexOf(status)
  if (idx === -1) return <span className={`badge ${STATUS_BADGE[status]}`}>{REQ_STATUS[status]}</span>
  return (
    <div className="status-flow">
      {REQ_FLOW.map((s, i) => (
        <span key={s} className={`status-step ${i < idx ? 'done' : i === idx ? 'current' : ''}`}>{REQ_STATUS[s]}</span>
      ))}
    </div>
  )
}

export default function RequestDetail() {
  const { id } = useParams()
  const { user, hasRole } = useAuth()
  const [req, setReq] = useState(null)
  const [offers, setOffers] = useState([])
  const [ai, setAi] = useState(null)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [offerForm, setOfferForm] = useState({ message: '', conditions: '' })
  const [profs, setProfs] = useState([])

  const load = () => {
    api(`/requests/${id}`).then(setReq).catch(e => setErr(e.message))
    api(`/requests/${id}/offers`).then(setOffers).catch(() => {})
    api(`/ai/match-professors/${id}`).then(setAi).catch(() => {})
  }
  useEffect(load, [id])
  useEffect(() => { if (req && req.student_id === user?.id) api('/profiles/professors').then(setProfs).catch(() => {}) }, [req])

  if (err && !req) return <div className="error-box">{err}</div>
  if (!req) return <div className="empty">در حال بارگذاری…</div>

  const isOwner = req.student_id === user.id
  const isManager = hasRole('research_manager', 'system_admin')
  const isProf = hasRole('professor')
  const act = async (action, reason = '') => {
    setErr(''); setMsg('')
    try {
      const r = await api(`/requests/${id}/status`, { method: 'POST', body: { action, reason } })
      setReq(r); setMsg('وضعیت به‌روزرسانی شد.')
    } catch (e) { setErr(e.message) }
  }
  const announce = async () => {
    setErr(''); setMsg('')
    try {
      await api(`/requests/${id}/offers`, { method: 'POST', body: offerForm })
      setOfferForm({ message: '', conditions: '' }); setMsg('اعلام آمادگی ثبت شد.'); load()
    } catch (e) { setErr(e.message) }
  }
  const offerAction = async (offerId, action) => {
    setErr(''); setMsg('')
    try {
      if (action === 'accept') {
        const r = await api(`/offers/${offerId}/accept`, { method: 'POST' })
        setMsg(r.message)
        if (r.project_id) setTimeout(() => { window.location.assign(`/projects/${r.project_id}`) }, 1200)
      } else if (action === 'reject') {
        await api(`/offers/${offerId}/reject`, { method: 'POST' }); setMsg('پیشنهاد رد شد.')
      } else if (action === 'dialogue') {
        const r = await api(`/offers/${offerId}/start-dialogue`, { method: 'POST' })
        window.location.assign(`/chat/${id}`)
        return
      }
      load()
    } catch (e) { setErr(e.message) }
  }
  const shareSecret = async (professorId) => {
    try { await api(`/requests/${id}/share-secret`, { method: 'POST', body: { professor_id: Number(professorId) } }); setMsg('دسترسی محرمانه داده شد.'); load() }
    catch (e) { setErr(e.message) }
  }
  const attach = async (file) => {
    try { await uploadFile(`/requests/${id}/attachments`, file); setMsg('فایل پیوست شد.'); }
    catch (e) { setErr(e.message) }
  }

  return (
    <>
      {err && <div className="error-box">{err}</div>}
      {msg && <div className="ok-box">{msg}</div>}
      <div className="card">
        <div className="row">
          <h3 style={{ flex: 2, margin: 0 }}>{req.title}</h3>
          <span className={`badge ${STATUS_BADGE[req.status]}`}>{REQ_STATUS[req.status]}</span>
        </div>
        <Stepper status={req.status} />
        <div className="hint">دانشجو: {req.student_name} | حوزه: {req.field || '—'} | زمان‌بندی: {req.timeline || '—'} | {SCOPE_LABEL[req.scope]}</div>
        {req.summary && <div style={{ marginTop: 8 }}><b>خلاصه قابل نمایش:</b> {req.summary}</div>}
        {req.problem && <div style={{ marginTop: 6 }}><b>شرح مسئله:</b> {req.problem}</div>}
        {req.goals && <div><b>اهداف:</b> {req.goals}</div>}
        {req.skills?.length > 0 && <div className="hint">مهارت‌های لازم: {req.skills.join('، ')}</div>}
        {req.secret_details && (isOwner || isManager) && (
          <div className="demo-banner" style={{ background: '#fef2f2', borderColor: '#f87171', color: '#991b1b' }}>
            <b>جزئیات محرمانه (فقط شما و اشتراک‌گرفتگان):</b> {req.secret_details}
          </div>
        )}
        {isOwner && (
          <div className="row" style={{ marginTop: 12 }}>
            <input type="file" onChange={e => e.target.files?.[0] && attach(e.target.files[0])} style={{ maxWidth: 260 }} />
            {isOwner && profs.length > 0 && req.secret_details && (
              <select defaultValue="" onChange={e => e.target.value && shareSecret(e.target.value)} style={{ maxWidth: 260 }}>
                <option value="">اشتراک جزئیات محرمانه با…</option>
                {profs.map(p => <option key={p.user_id} value={p.user_id}>{p.display_name}</option>)}
              </select>
            )}
            {req.status === 'draft' && <button className="btn" onClick={() => act('publish')}>🚀 انتشار در استخر</button>}
            {['draft', 'published', 'offers_received', 'negotiating'].includes(req.status) && (
              <button className="btn danger" onClick={() => act('cancel', 'لغو توسط دانشجو')}>لغو درخواست</button>
            )}
          </div>
        )}
        {isManager && req.status === 'pending_university_approval' && (
          <div className="ok-box">
            در انتظار تأیید دانشگاه است.
            <button className="btn" style={{ marginInlineStart: 10 }} onClick={async () => {
              try {
                const r = await api(`/requests/${id}/approve`, { method: 'POST' })
                window.location.assign(`/projects/${r.project_id}`)
              } catch (e) { setErr(e.message) }
            }}>✅ تأیید و تشکیل پروژه</button>
          </div>
        )}
      </div>

      {isProf && !req.my_offer && ['published', 'offers_received', 'negotiating'].includes(req.status) && (
        <div className="card">
          <h3>اعلام آمادگی برای همکاری</h3>
          <label className="fld">توضیح شما</label>
          <textarea rows={2} value={offerForm.message} onChange={e => setOfferForm({ ...offerForm, message: e.target.value })} placeholder="چرا این موضوع با تخصص شما هم‌خوانی دارد؟" />
          <label className="fld">شرایط پیشنهادی (جلسات، گزارش‌دهی و…)</label>
          <input value={offerForm.conditions} onChange={e => setOfferForm({ ...offerForm, conditions: e.target.value })} />
          <button className="btn" style={{ marginTop: 10 }} onClick={announce}>🤝 اعلام آمادگی</button>
        </div>
      )}
      {req.my_offer && (
        <div className="card">
          <h3>اعلام آمادگی شما <span className="badge">{OFFER_STATUS[req.my_offer.status]}</span></h3>
          <div>{req.my_offer.message}</div>
          <div className="hint">{req.my_offer.conditions}</div>
        </div>
      )}

      {(isOwner || isManager) && (
        <div className="card">
          <h3>پیشنهادهای اساتید ({offers.length})</h3>
          {offers.length === 0 && <div className="empty">هنوز اعلام آمادگی ثبت نشده است.</div>}
          <table className="tbl">
            <thead><tr><th>استاد</th><th>توضیح</th><th>شرایط</th><th>وضعیت</th><th>اقدام</th></tr></thead>
            <tbody>
              {offers.map(o => (
                <tr key={o.id}>
                  <td><b>{o.professor_name}</b></td>
                  <td>{o.message}</td>
                  <td className="hint">{o.conditions}</td>
                  <td><span className="badge">{OFFER_STATUS[o.status]}</span></td>
                  <td>
                    {isOwner && ['sent', 'viewed', 'in_dialogue'].includes(o.status) && (
                      <div className="row" style={{ gap: 6 }}>
                        <button className="btn small" onClick={() => offerAction(o.id, 'accept')}>✅ پذیرش</button>
                        <button className="btn small secondary" onClick={() => offerAction(o.id, 'dialogue')}>💬 گفت‌وگو</button>
                        <button className="btn small danger" onClick={() => offerAction(o.id, 'reject')}>رد</button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="hint" style={{ marginTop: 8 }}>
            پذیرش یک پیشنهاد، سایر پیشنهادهای در جریان را «جایگزین‌شده» می‌کند؛ پس از پذیرش، توافق‌نامه همکاری برای امضای دوطرفه نمایش داده می‌شود.
          </div>
        </div>
      )}

      {ai && ai.suggestions?.length > 0 && (
        <div className="card">
          <h3>🤖 پیشنهاد تطبیق هوشمند (آزمایشی)</h3>
          <div className="demo-banner">{ai.disclaimer} {ai.note}</div>
          <div className="grid cols-2">
            {ai.suggestions.slice(0, 4).map(s => (
              <div key={s.professor_id} className="stat">
                <b>{s.professor_name}</b> <span className="badge teal">امتیاز نمایشی {s.score}</span>
                <ul style={{ margin: '6px 0 0', paddingRight: 18, fontSize: 12.5 }}>
                  {s.reasons.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  )
}
