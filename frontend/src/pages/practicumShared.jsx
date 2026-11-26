import React, { useEffect, useState } from 'react'
import { api, toFa, fmtDateTime } from '../api.js'

export const STATUS_BADGE = {
  active: 'gray', awaiting_review: 'amber', needs_revision: 'red', approved: 'green', cancelled: 'gray',
}
export const WORK_BADGE = { pending: 'amber', approved: 'green', needs_revision: 'red' }
export const INTERVAL_FA = { daily: 'روزانه', weekly: 'هفتگی' }

export async function downloadFile(fileId, name) {
  const { getToken } = await import('../api.js')
  const res = await fetch(`/api/v1/files/${fileId}`, { headers: { Authorization: `Bearer ${getToken()}` } })
  if (!res.ok) { alert('دانلود فایل ناموفق بود'); return }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name || 'report'
  a.click()
  URL.revokeObjectURL(url)
}

/* فرم ثبت درس عملی — onlyType فقط همان نوع را می‌گذارد (صفحهٔ کارآموزی)؛
   بدون آن کارآموزی حذف می‌شود (صفحهٔ درس‌پروژه و تحقیق و ارائه) */
export function CreateForm({ meta, onDone, onlyType, title = '➕ ثبت درس عملی جدید' }) {
  const allowed = (meta?.courses || []).filter(c => c.allowed && (onlyType ? c.key === onlyType : c.key !== 'internship'))
  const [profs, setProfs] = useState([])
  const [draft, setDraft] = useState({ course_type: '', title: '', semester: '', description: '', supervisor_id: '' })
  const [busy, setBusy] = useState(false)

  useEffect(() => { api('/profiles/professors').then(setProfs).catch(() => {}) }, [])
  useEffect(() => {
    if (allowed.length && !allowed.some(c => c.key === draft.course_type)) {
      setDraft(d => ({ ...d, course_type: allowed[0].key }))
    }
  }, [meta?.my_degree_key])

  const create = async () => {
    if (!draft.title.trim()) return alert(onlyType === 'internship' ? 'عنوان محل کارآموزی را بنویسید' : 'عنوان درس را بنویسید')
    if (!draft.supervisor_id) return alert('استاد مربوطه را انتخاب کنید')
    setBusy(true)
    try {
      await api('/practicum/', { method: 'POST', body: { ...draft, supervisor_id: Number(draft.supervisor_id) } })
      setDraft(d => ({ ...d, title: '', description: '', semester: '' }))
      onDone()
    } catch (e) { alert(e.message) } finally { setBusy(false) }
  }

  if (!allowed.length) return null
  return (
    <div className="card">
      <h4>{title}</h4>
      <div className="grid cols-2" style={{ marginTop: 8 }}>
        <div>
          <label className="fld">استاد مربوطه / ارزیاب</label>
          <select value={draft.supervisor_id} onChange={e => setDraft({ ...draft, supervisor_id: e.target.value })}>
            <option value="">— انتخاب استاد —</option>
            {profs.map(p => <option key={p.user_id} value={p.user_id}>{p.display_name} — {p.field_of_study}</option>)}
          </select>
        </div>
        <div>
          <label className="fld">نیم‌سال / ترم (اختیاری)</label>
          <input placeholder="مثلاً: نیم‌سال اول ۱۴۰۴-۱۴۰۵"
                 value={draft.semester} onChange={e => setDraft({ ...draft, semester: e.target.value })} />
        </div>
      </div>
      <label className="fld">عنوان {onlyType === 'internship' ? 'محل کارآموزی' : 'درس'}</label>
      <input placeholder={onlyType === 'internship' ? 'مثلاً: کارآموزی در شرکت نرم‌افزاری «داده»'
        : 'مثلاً: طراحی و پیاده‌سازی سامانهٔ تحلیل داده'}
             value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} />
      <label className="fld">شرح {onlyType === 'internship' ? 'محل کارآموزی و وظایف' : 'موضوع درس‌پروژه'}</label>
      <textarea rows={2} placeholder="شرح کوتاه…"
                value={draft.description} onChange={e => setDraft({ ...draft, description: e.target.value })} />
      <div className="row" style={{ marginTop: 10 }}>
        <button className="btn" onClick={create} disabled={busy}>{busy ? 'در حال ثبت…' : 'ثبت درس و اطلاع به استاد'}</button>
      </div>
    </div>
  )
}

/* تنظیم زمان‌بندی گزارش کار کارآموزی — فقط استاد مربوطه */
function ScheduleCard({ rec, onChanged }) {
  const [draft, setDraft] = useState({ report_interval: rec.report_interval || 'weekly', min_reports: rec.min_reports || 5 })
  const [busy, setBusy] = useState(false)

  const save = async () => {
    setBusy(true)
    try {
      await api(`/practicum/${rec.id}/schedule`, { method: 'POST', body: { ...draft, min_reports: Number(draft.min_reports) } })
      onChanged()
    } catch (e) { alert(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="card" style={{ borderRight: '4px solid var(--warn)' }}>
      <h4>🗓️ زمان‌بندی گزارش کار (تعیین استاد مربوطه)</h4>
      <div className="hint">
        مسیر گزارش کار به زمان‌بندی شما وابسته است: برخی اساتید گزارش روزانه می‌خواهند و برخی هفتگی.
        در طول یک ترم حداقل {toFa(Math.max(5, Number(draft.min_reports) || 5))} گزارش کار برای تأیید نهایی کارآموزی لازم است.
      </div>
      <div className="row" style={{ gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
        <select value={draft.report_interval} onChange={e => setDraft({ ...draft, report_interval: e.target.value })} style={{ maxWidth: 220 }}>
          <option value="weekly">گزارش هفتگی</option>
          <option value="daily">گزارش روزانه</option>
        </select>
        <input type="number" min="5" max="30" style={{ maxWidth: 220 }}
               value={draft.min_reports}
               onChange={e => setDraft({ ...draft, min_reports: e.target.value })}
               title="حداقل تعداد گزارش کار در ترم" />
        <button className="btn small" onClick={save} disabled={busy}>{busy ? 'در حال ثبت…' : 'ثبت زمان‌بندی و اطلاع به دانشجو'}</button>
      </div>
      <div className="hint" style={{ marginTop: 6 }}>
        وضعیت فعلی: {INTERVAL_FA[rec.report_interval] || 'هفتگی'} · ارسال‌شده: {toFa(rec.report_count)} از حداقل {toFa(rec.min_reports)}
      </div>
    </div>
  )
}

/* فرم گزارش کار کارآموزی — دانشجو */
function WorkReportForm({ rec, onDone }) {
  const [draft, setDraft] = useState({ title: '', content: '', hours: '' })
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!draft.title.trim()) return alert('عنوان گزارش کار را بنویسید (مثلاً «گزارش هفتهٔ اول»)')
    if (!draft.content.trim()) return alert('شرح کار انجام‌شده را بنویسید')
    setBusy(true)
    try {
      await api(`/practicum/${rec.id}/work-reports`, { method: 'POST', body: {
        title: draft.title, content: draft.content,
        hours: draft.hours === '' ? null : Number(draft.hours) } })
      setDraft({ title: '', content: '', hours: '' })
      onDone()
    } catch (e) { alert(e.message) } finally { setBusy(false) }
  }

  const n = (rec.report_count || 0) + 1
  return (
    <div className="card">
      <h4>📝 ارسال گزارش کار — شمارهٔ {toFa(n)}</h4>
      <div className="hint">
        زمان‌بندی تعیین‌شدهٔ استاد: <b>{INTERVAL_FA[rec.report_interval] || 'هفتگی'}</b> · برای تأیید نهایی کارآموزی
        حداقل <b>{toFa(rec.min_reports)}</b> گزارش کار در ترم لازم است. تاکنون: {toFa(rec.report_count)} گزارش.
      </div>
      <input placeholder="مثلاً: گزارش هفتهٔ اول — آشنایی با محیط کار و وظایف"
             value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} />
      <textarea rows={3} placeholder="چه کارهایی انجام دادید؟ چه آموختید؟ مشکلات و راه‌حل‌ها…"
                value={draft.content} onChange={e => setDraft({ ...draft, content: e.target.value })} />
      <div className="row" style={{ marginTop: 8 }}>
        <input type="number" min="0" step="0.5" placeholder="ساعت کارکرد (اختیاری)" style={{ maxWidth: 220 }}
               value={draft.hours} onChange={e => setDraft({ ...draft, hours: e.target.value })} />
        <button className="btn" onClick={submit} disabled={busy}>
          {busy ? 'در حال ارسال…' : 'ثبت گزارش کار و اطلاع به استاد'}
        </button>
      </div>
    </div>
  )
}

/* فهرست گزارش‌های کار + ارزیابی استاد */
function WorkReportsCard({ rec, isSupervisor, onChanged }) {
  const [review, setReview] = useState({ id: null, feedback: '' })
  const rows = rec.work_reports || []

  const doReview = async (wid, decision) => {
    try {
      await api(`/practicum/work-reports/${wid}/review`, { method: 'POST', body: {
        decision, feedback: review.feedback } })
      setReview({ id: null, feedback: '' })
      onChanged()
    } catch (e) { alert(e.message) }
  }

  return (
    <div className="card">
      <h4>📔 گزارش‌های کار ({toFa(rows.length)}) — زمان‌بندی: {INTERVAL_FA[rec.report_interval] || 'هفتگی'}</h4>
      <div className="rounds">
        {rows.map(w => (
          <div key={w.id} className="round-item">
            <div className="round-head">
              <b>گزارش {toFa(w.report_no)}</b>
              <span className={`badge ${WORK_BADGE[w.status]}`}>{w.status_fa}</span>
              <span className="hint">{fmtDateTime(w.created_at)}</span>
              {w.hours != null && <span className="badge teal">{toFa(w.hours)} ساعت</span>}
            </div>
            <b style={{ fontSize: 13.2 }}>{w.title}</b>
            {w.content && <div style={{ fontSize: 13.2 }}>{w.content}</div>}
            {w.status !== 'pending' && w.feedback && (
              <div className="feedback-box">
                <b style={{ color: w.status === 'approved' ? 'var(--success)' : 'var(--warn)' }}>
                  {w.status === 'approved' ? '✅ بازخورد استاد (تأیید):' : '↩️ بازخورد استاد (اصلاح لازم):'}
                </b> {w.feedback}
                <div className="hint" style={{ marginTop: 2 }}>{fmtDateTime(w.reviewed_at)}</div>
              </div>
            )}
            {isSupervisor && w.status === 'pending' && (
              review.id === w.id ? (
                <div style={{ marginTop: 6 }}>
                  <textarea rows={2} placeholder="بازخورد استاد…" value={review.feedback}
                            onChange={e => setReview({ ...review, feedback: e.target.value })} />
                  <div className="row" style={{ gap: 6, marginTop: 6 }}>
                    <button className="btn secondary small" onClick={() => doReview(w.id, 'needs_revision')}>↩️ اصلاح لازم</button>
                    <button className="btn small" onClick={() => doReview(w.id, 'approved')}>✅ پذیرش گزارش</button>
                  </div>
                </div>
              ) : (
                <button className="btn ghost small" style={{ marginTop: 6 }}
                        onClick={() => setReview({ id: w.id, feedback: '' })}>🧑‍⚖️ ارزیابی این گزارش</button>
              )
            )}
          </div>
        ))}
        {rows.length === 0 && <div className="empty">هنوز گزارش کاری ثبت نشده است.</div>}
      </div>
    </div>
  )
}

/* نمای کامل رکورد — درس‌پروژه/تحقیق و ارائه با چرخهٔ نوبت‌ها؛ کارآموزی با گزارش کار اضافه */
export function RecordDetail({ id, onBack, user }) {
  const [rec, setRec] = useState(null)
  const [note, setNote] = useState('')
  const [files, setFiles] = useState([])
  const [busy, setBusy] = useState(false)
  const [review, setReview] = useState({ feedback: '', score: '' })

  const load = () => api(`/practicum/${id}`).then(setRec).catch(e => alert(e.message))
  useEffect(() => { load() }, [id])
  if (!rec) return <div className="card hint">در حال بارگذاری…</div>

  const isOwner = user.id === rec.student_id
  const isSupervisor = user.id === rec.supervisor_id
  const isInternship = rec.course_type === 'internship'
  const openRound = rec.submissions.find(s => s.status === 'pending')
  const workOk = !isInternship || (rec.report_count || 0) >= (rec.min_reports || 5)
  const flow = [
    [isInternship ? 'گزارش‌های کار' : 'ارسال گزارش', isInternship ? (rec.report_count || 0) > 0 : rec.round_count > 0],
    ['ارزیابی استاد', rec.submissions.some(s => s.status !== 'pending')],
    ['اصلاح و نوبت بعد', rec.submissions.some(s => s.status === 'needs_revision')],
    ['تأیید نهایی', rec.status === 'approved'],
  ]

  const submit = async () => {
    if (!note.trim() && files.length === 0) return alert('متن گزارش یا حداقل یک فایل لازم است')
    setBusy(true)
    try {
      await api(`/practicum/${id}/submissions`, { method: 'POST', form: (() => {
        const fd = new FormData()
        fd.append('note', note)
        files.forEach(f => fd.append('files', f))
        return fd
      })() })
      setNote(''); setFiles([]); document.getElementById('practicum-files') && (document.getElementById('practicum-files').value = '')
      load()
    } catch (e) { alert(e.message) } finally { setBusy(false) }
  }

  const doReview = async (decision) => {
    if (!review.feedback.trim()) return alert('بازخورد برای دانشجو بنویسید — حتی در تأیید نهایی توصیه می‌شود.')
    const score = review.score === '' ? null : Number(review.score)
    if (decision === 'approved' && score !== null && (score < 0 || score > 20)) return alert('نمره باید بین ۰ تا ۲۰ باشد')
    try {
      const s = openRound
      await api(`/practicum/submissions/${s.id}/review`, { method: 'POST', body: {
        decision, feedback: review.feedback, score } })
      setReview({ feedback: '', score: '' })
      load()
    } catch (e) { alert(e.message) }
  }

  const cancel = async () => {
    if (!confirm('این رکورد درس لغو شود؟')) return
    await api(`/practicum/${id}/cancel`, { method: 'POST' }).catch(e => alert(e.message))
    load()
  }

  return (
    <>
      <div className="card">
        <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap' }}>
          <h3 style={{ margin: 0 }}>📘 {rec.title} <span className={`badge ${STATUS_BADGE[rec.status]}`}>{rec.status_fa}</span></h3>
          <button className="btn ghost small" onClick={onBack}>← بازگشت به فهرست</button>
        </div>
        <div className="hint" style={{ marginTop: 6 }}>
          {rec.course_fa} · مقطع: {rec.degree_fa} · دانشجو: {rec.student_name} · استاد مربوطه: {rec.supervisor_name}
          {rec.semester ? ` · ${rec.semester}` : ''} · نوبت‌ها: {toFa(rec.round_count)}
          {isInternship && <> · گزارش کار: <b>{toFa(rec.report_count)}</b> از حداقل {toFa(rec.min_reports)} ({INTERVAL_FA[rec.report_interval] || 'هفتگی'})</>}
          {rec.final_score != null && <> · <b>نمرهٔ نهایی: {toFa(rec.final_score)}</b> از ۲۰</>}
        </div>
        <div className="status-flow">
          {flow.map(([label, done]) => <span key={label} className={`status-step ${done ? 'done' : ''}`}>{done ? '✓ ' : ''}{label}</span>)}
        </div>
        {rec.description && <div className="hint">{rec.description}</div>}
        {rec.status === 'approved' && rec.supervisor_note && (
          <div className="ok-box">✅ جمع‌بندی استاد: {rec.supervisor_note}</div>
        )}
        {isOwner && rec.status !== 'approved' && rec.status !== 'cancelled' && (
          <button className="btn ghost small" style={{ marginTop: 8 }} onClick={cancel}>لغو این درس</button>
        )}
      </div>

      {isInternship && isSupervisor && rec.status !== 'approved' && rec.status !== 'cancelled'
        && <ScheduleCard rec={rec} onChanged={load} />}
      {isInternship && isOwner && rec.status !== 'approved' && rec.status !== 'cancelled'
        && <WorkReportForm rec={rec} onDone={load} />}
      {isInternship && <WorkReportsCard rec={rec} isSupervisor={isSupervisor} onChanged={load} />}

      {/* فرم ارسال نوبت جدید — دانشجو */}
      {isOwner && rec.status !== 'approved' && rec.status !== 'cancelled' && (
        <div className="card">
          <h4>📤 ارسال گزارش پیشرفت — نوبت {toFa(rec.round_count + 1)}</h4>
          {isInternship && !workOk && (
            <div className="error-box">
              ⚠️ تأیید نهایی کارآموزی فقط با حداقل {toFa(rec.min_reports)} گزارش کار ممکن است —
              تاکنون {toFa(rec.report_count)} گزارش ثبت شده؛ ابتدا گزارش‌های کار را کامل کنید.
            </div>
          )}
          <textarea rows={3} placeholder="خلاصهٔ کار انجام‌شده در این نوبت، اصلاحات انجام‌شده طبق بازخورد استاد…"
                    value={note} onChange={e => setNote(e.target.value)} />
          <div className="row" style={{ marginTop: 8 }}>
            <input type="file" id="practicum-files" multiple
                   onChange={e => setFiles([...(e.target.files || [])])} />
            <button className="btn" onClick={submit} disabled={busy}>
              {busy ? 'در حال ارسال…' : 'ارسال برای ارزیابی استاد'}
            </button>
          </div>
          <div className="hint" style={{ marginTop: 6 }}>
            حداکثر ۵ فایل و هر فایل تا ۱۵ مگابایت (گزارش، پیوست کد، عکس محیط کارآموزی و…).
            تا ارزیابی استاد، وضعیت «در انتظار ارزیابی» می‌ماند.
          </div>
        </div>
      )}

      {/* فرم ارزیابی — استاد مربوطه */}
      {isSupervisor && openRound && (
        <div className="card" style={{ borderRight: '4px solid var(--accent)' }}>
          <h4>🧑‍⚖️ ارزیابی نوبت {toFa(openRound.round_no)}</h4>
          <div className="hint">بازخورد شفاف بنویسید؛ برای ادامهٔ کار دانشجو «اصلاح لازم» و برای پایان درس «تأیید نهایی» را بزنید.</div>
          {isInternship && !workOk && (
            <div className="error-box">
              برای تأیید نهایی این کارآموزی، حداقل {toFa(rec.min_reports)} گزارش کار لازم است
              (تاکنون {toFa(rec.report_count)}) — می‌توانید نوبت را «اصلاح لازم» بزنید تا دانشجو گزارش‌های کار را کامل کند.
            </div>
          )}
          <textarea rows={3} placeholder="بازخورد: چه چیز خوب است، چه چیز باید اصلاح شود…"
                    value={review.feedback} onChange={e => setReview({ ...review, feedback: e.target.value })} />
          <div className="row" style={{ marginTop: 8 }}>
            <input type="number" min="0" max="20" step="0.25" placeholder="نمره (اختیاری — فقط هنگام تأیید نهایی)"
                   value={review.score} onChange={e => setReview({ ...review, score: e.target.value })} />
          </div>
          <div className="row" style={{ marginTop: 10 }}>
            <button className="btn secondary" onClick={() => doReview('needs_revision')}>↩️ درخواست اصلاح</button>
            <button className="btn" onClick={() => doReview('approved')}>✅ تأیید نهایی درس</button>
          </div>
          <div className="hint" style={{ marginTop: 6 }}>با تأیید نهایی، درس بسته می‌شود و نمرهٔ واردشده به‌عنوان نمرهٔ نهایی ثبت می‌گردد.</div>
        </div>
      )}

      {/* تایم‌لاین نوبت‌ها */}
      <div className="card">
        <h4>🕰️ چرخهٔ ارسال و بازخورد ({toFa(rec.submissions.length)} نوبت)</h4>
        <div className="rounds">
          {rec.submissions.map(s => (
            <div key={s.id} className="round-item">
              <div className="round-head">
                <b>نوبت {toFa(s.round_no)}</b>
                <span className={`badge ${s.status === 'approved' ? 'green' : s.status === 'needs_revision' ? 'red' : 'amber'}`}>{s.status_fa}</span>
                <span className="hint">{fmtDateTime(s.created_at)}</span>
                {s.score != null && <span className="badge teal">نمرهٔ نوبت: {toFa(s.score)}</span>}
              </div>
              {s.note && <div style={{ fontSize: 13.2 }}>{s.note}</div>}
              {s.files.length > 0 && (
                <div className="files">
                  {s.files.map(f => (
                    <a key={f.id} className="file-chip" href="#"
                       onClickCapture={e => { e.preventDefault(); downloadFile(f.id, f.name) }}>
                      📎 {f.name} ({toFa(Math.round((f.size || 0) / 1024))}KB)
                    </a>
                  ))}
                </div>
              )}
              {s.status !== 'pending' && s.feedback && (
                <div className="feedback-box">
                  <b style={{ color: s.status === 'approved' ? 'var(--success)' : 'var(--warn)' }}>
                    {s.status === 'approved' ? '✅ بازخورد استاد (تأیید):' : '↩️ بازخورد استاد (اصلاح لازم):'}
                  </b> {s.feedback}
                  {s.supervisor_note && <div className="hint" style={{ marginTop: 4 }}>توضیح تکمیلی: {s.supervisor_note}</div>}
                  <div className="hint" style={{ marginTop: 2 }}>{fmtDateTime(s.reviewed_at)}</div>
                </div>
              )}
            </div>
          ))}
          {rec.submissions.length === 0 && <div className="empty">هنوز نوبتی ارسال نشده است.</div>}
        </div>
      </div>
    </>
  )
}
