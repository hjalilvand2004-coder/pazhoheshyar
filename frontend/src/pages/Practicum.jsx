import React, { useEffect, useState } from 'react'
import { useAuth } from '../auth.jsx'
import { api, toFa, fmtDateTime } from '../api.js'

const STATUS_BADGE = {
  active: 'gray', awaiting_review: 'amber', needs_revision: 'red', approved: 'green', cancelled: 'gray',
}

async function downloadFile(fileId, name) {
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

export default function Practicum() {
  const { user } = useAuth()
  const [meta, setMeta] = useState(null)
  const [records, setRecords] = useState([])
  const [openId, setOpenId] = useState(null)

  const isStudent = (user?.roles || []).includes('student')
  const isManager = (user?.roles || []).some(r => ['research_manager', 'system_admin'].includes(r))
  const load = () => {
    const path = isStudent ? '/practicum/mine' : isManager ? '/practicum/all' : '/practicum/supervised'
    api(path).then(setRecords).catch(e => alert(e.message))
    api('/practicum/meta').then(setMeta).catch(() => {})
  }
  useEffect(() => { load() }, [])
  if (openId) return <RecordDetail id={openId} onBack={() => { setOpenId(null); load() }} user={user} />

  const allowed = (meta?.courses || []).filter(c => c.allowed)

  return (
    <>
      <div className="card">
        <h3>🛠️ کارآموزی، درس‌پروژه و تحقیق و ارائه — نسبت به مقطع تحصیلی</h3>
        {meta?.my_degree ? (
          <div className="demo-banner">
            <b>🎓 مقطع شما: {meta.degree_fa}</b> — درس‌های مجاز شما:
            {allowed.map(c => <span key={c.key} className="badge teal" style={{ margin: '0 3px' }}>{c.fa}</span>)}
            {allowed.length === 0 && <span> برای مقطع شما درس عملی ثبت نمی‌شود؛ از فضای پژوهش و پروژه‌ها استفاده کنید.</span>}
          </div>
        ) : (
          <div className="error-box">مقطع تحصیلی در پروفایل شما ثبت نشده — از «پروفایل پژوهشی» مقطع را انتخاب کنید تا درس‌های مجاز نمایش داده شود.</div>
        )}
        <div className="hint" style={{ marginTop: 8 }}>
          چرخهٔ هر درس: <b>ارسال گزارش پیشرفت</b> ← <b>ارزیابی و بازخورد استاد مربوطه</b> ← <b>اصلاح در نوبت بعد</b> ← …
          تا تأیید نهایی با ثبت نمره. {meta?.round_guidance || 'معمولاً ۴ تا ۵ نوبت رفت‌وبرگشت لازم است.'}
        </div>
      </div>

      {isStudent && <CreateForm meta={meta} onDone={load} />}
      {!isStudent && <div className="card"><h4>📥 درس‌های {isManager ? 'همهٔ دانشجویان' : 'تحت ارزیابی من'} ({toFa(records.length)})</h4></div>}

      <div className="grid cols-2">
        {records.map(r => (
          <div key={r.id} className="card">
            <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap' }}>
              <h4 style={{ margin: 0 }}>📘 {r.title}</h4>
              <span className={`badge ${STATUS_BADGE[r.status]}`}>{r.status_fa}</span>
            </div>
            <div className="hint" style={{ marginTop: 6 }}>
              {r.course_fa} · مقطع: {r.degree_fa} ·
              {isStudent ? ` استاد مربوطه: ${r.supervisor_name}` : ` دانشجو: ${r.student_name}`}
              {r.semester ? ` · ${r.semester}` : ''}
            </div>
            <div className="hint">نوبت‌های ارسال: {toFa(r.round_count)} {r.final_score != null && `· نمرهٔ نهایی: ${toFa(r.final_score)}`}</div>
            <div className="row" style={{ gap: 6, marginTop: 8 }}>
              <button className="btn small" onClick={() => setOpenId(r.id)}>نمایش چرخهٔ ارسال و بازخورد</button>
            </div>
          </div>
        ))}
        {records.length === 0 && (
          <div className="fancy-empty" style={{ gridColumn: '1 / -1' }}>
            <div className="big">🛠️</div>
            {isStudent
              ? 'هنوز درس عملی ثبت نکرده‌اید — با فرم بالای صفحه اولین کارآموزی/درس‌پروژه را بسازید.'
              : 'هنوز رکوردی برای ارزیابی دارید نیست.'}
          </div>
        )}
      </div>
    </>
  )
}

function CreateForm({ meta, onDone }) {
  const allowed = (meta?.courses || []).filter(c => c.allowed)
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
    if (!draft.title.trim()) return alert('عنوان درس را بنویسید')
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
      <h4>➕ ثبت درس عملی جدید</h4>
      <div className="grid cols-2" style={{ marginTop: 8 }}>
        <div>
          <label className="fld">نوع درس (مطابق مقطع شما)</label>
          <select value={draft.course_type} onChange={e => setDraft({ ...draft, course_type: e.target.value })}>
            {allowed.map(c => <option key={c.key} value={c.key}>{c.fa}</option>)}
          </select>
        </div>
        <div>
          <label className="fld">استاد مربوطه / ارزیاب</label>
          <select value={draft.supervisor_id} onChange={e => setDraft({ ...draft, supervisor_id: e.target.value })}>
            <option value="">— انتخاب استاد —</option>
            {profs.map(p => <option key={p.user_id} value={p.user_id}>{p.display_name} — {p.field_of_study}</option>)}
          </select>
        </div>
        <div>
          <label className="fld">عنوان درس</label>
          <input placeholder="مثلاً: کارآموزی در شرکت نرم‌افزاری «داده»"
                 value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} />
        </div>
        <div>
          <label className="fld">نیم‌سال / ترم (اختیاری)</label>
          <input placeholder="مثلاً: نیم‌سال اول ۱۴۰۴-۱۴۰۵"
                 value={draft.semester} onChange={e => setDraft({ ...draft, semester: e.target.value })} />
        </div>
      </div>
      <label className="fld">شرح محل کارآموزی یا موضوع درس‌پروژه</label>
      <textarea rows={2} placeholder="شرح کوتاه محل کارآموزی، وظایف یا موضوع پروژه…"
                value={draft.description} onChange={e => setDraft({ ...draft, description: e.target.value })} />
      <div className="row" style={{ marginTop: 10 }}>
        <button className="btn" onClick={create} disabled={busy}>{busy ? 'در حال ثبت…' : 'ثبت درس و اطلاع به استاد'}</button>
      </div>
    </div>
  )
}

function RecordDetail({ id, onBack, user }) {
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
  const openRound = rec.submissions.find(s => s.status === 'pending')
  const flow = [
    ['ارسال گزارش', rec.round_count > 0],
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

      {/* فرم ارسال نوبت جدید — دانشجو */}
      {isOwner && rec.status !== 'approved' && rec.status !== 'cancelled' && (
        <div className="card">
          <h4>📤 ارسال گزارش پیشرفت — نوبت {toFa(rec.round_count + 1)}</h4>
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
                    <a key={f.id} className="file-chip" onClick={() => downloadFile(f.id, f.name)} href="#" onClickCapture={e => { e.preventDefault(); downloadFile(f.id, f.name) }}>
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
