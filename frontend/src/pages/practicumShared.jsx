import React, { useEffect, useState } from 'react'
import { api, toFa, fmtDateTime } from '../api.js'

export const STATUS_BADGE = {
  pending_acceptance: 'amber', active: 'gray', awaiting_review: 'amber', needs_revision: 'red',
  approved: 'green', cancelled: 'gray',
}
export const INTERVAL_FA = { daily: 'روزانه', weekly: 'هفتگی', biweekly: 'دوهفته‌یکبار' }
export const LIKERT_LABELS = ['۰ — خیلی ضعیف', '۱ — ضعیف', '۲ — متوسط', '۳ — خوب', '۴ — عالی']
export const SCORE_MAX = 20   // سرجمع امتیاز لیکرت با سقف ۲۰ = نمرهٔ نهایی کارآموزی

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
        <button className="btn" onClick={create} disabled={busy}>{busy ? 'در حال ثبت…' : 'ثبت و ارسال برای استاد'}</button>
      </div>
    </div>
  )
}

/* پذیرش کارآموزی و تعیین زمان‌بندی گزارش پیشرفت — فقط استاد مربوطه */
export function AcceptCard({ rec, onChanged }) {
  const [draft, setDraft] = useState({
    report_interval: rec.report_interval || 'weekly',
    min_reports: rec.min_reports || 5,
  })
  const [busy, setBusy] = useState(false)
  const isPending = rec.status === 'pending_acceptance'

  const save = async () => {
    setBusy(true)
    try {
      await api(`/practicum/${rec.id}/accept`, { method: 'POST', body: { ...draft, min_reports: Number(draft.min_reports) } })
      onChanged()
    } catch (e) { alert(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="card" style={{ borderRight: '4px solid var(--warn)' }}>
      <h4>{isPending ? '✅ پذیرش کارآموزی و تعیین زمان‌بندی گزارش پیشرفت' : '🗓️ تغییر زمان‌بندی گزارش پیشرفت'}</h4>
      <div className="hint">
        با پذیرش، مبدأ زمان‌بندی از «تاریخ امروز» ثبت می‌شود و دانشجو از همان لحظه طبق برنامه
        گزارش پیشرفت می‌فرستد — بدون نیاز به تأیید هر مرحله. سرجمع امتیاز طیف لیکرت (۰ تا ۴)
        با سقف ۲۰، نمرهٔ کارآموزی از ۲۰ می‌شود.
      </div>
      <div className="row" style={{ gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
        <select value={draft.report_interval} onChange={e => setDraft({ ...draft, report_interval: e.target.value })} style={{ maxWidth: 220 }}>
          <option value="daily">گزارش روزانه</option>
          <option value="weekly">گزارش هفتگی</option>
          <option value="biweekly">گزارش دوهفته‌یکبار</option>
        </select>
        <input type="number" min="5" max="30" style={{ maxWidth: 220 }}
               value={draft.min_reports}
               onChange={e => setDraft({ ...draft, min_reports: e.target.value })}
               title="حداقل تعداد گزارش پیشرفت در ترم" />
        <button className="btn small" onClick={save} disabled={busy}>
          {busy ? 'در حال ثبت…' : isPending ? 'پذیرش و اطلاع به دانشجو' : 'ثبت زمان‌بندی جدید'}
        </button>
      </div>
      {!isPending && (
        <div className="hint" style={{ marginTop: 6 }}>
          وضعیت فعلی: {INTERVAL_FA[rec.report_interval] || 'هفتگی'} · مبدأ زمان‌بندی: {fmtDateTime(rec.accepted_at)} ·
          ثبت‌شده: {toFa(rec.round_count)} از حداقل {toFa(rec.min_reports)}
        </div>
      )}
    </div>
  )
}

/* فرم ثبت گزارش پیشرفت — دانشجو؛ در کارآموزی بدون انتظار تأیید مرحله‌ای */
export function SubmissionForm({ rec, onDone, internship }) {
  const [note, setNote] = useState('')
  const [files, setFiles] = useState([])
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!note.trim() && files.length === 0) return alert('متن گزارش یا حداقل یک فایل لازم است')
    setBusy(true)
    try {
      await api(`/practicum/${rec.id}/submissions`, { method: 'POST', form: (() => {
        const fd = new FormData()
        fd.append('note', note)
        files.forEach(f => fd.append('files', f))
        return fd
      })() })
      setNote(''); setFiles([]); document.getElementById('practicum-files') && (document.getElementById('practicum-files').value = '')
      onDone()
    } catch (e) { alert(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="card">
      <h4>📤 ثبت گزارش پیشرفت — {internship ? `شمارهٔ ${toFa(rec.round_count + 1)} طبق زمان‌بندی` : `نوبت ${toFa(rec.round_count + 1)}`}</h4>
      {internship ? (
        <div className="hint">
          زمان‌بندی تعیین‌شدهٔ استاد: <b>{INTERVAL_FA[rec.report_interval] || 'هفتگی'}</b> (از {fmtDateTime(rec.accepted_at)}) ·
          تاکنون {toFa(rec.round_count)} گزارش از حداقل {toFa(rec.min_reports)} ·
          گزارش‌ها را طبق برنامه بفرستید — نیازی به انتظار برای تأیید مرحلهٔ قبلی نیست؛ استاد هر گزارش را
          با طیف لیکرت ۰ تا ۴ امتیاز می‌دهد و سرجمع امتیازها نمرهٔ کارآموزی از ۲۰ می‌شود.
        </div>
      ) : (
        <div className="hint">گزارش این نوبت را بفرستید؛ پس از بازخورد استاد، اصلاحات را در نوبت بعدی ارسال کنید.</div>
      )}
      <textarea rows={3}
                placeholder={internship
                  ? 'چه کارهایی در این بازه انجام دادید؟ چه آموختید؟ مشکلات و راه‌حل‌ها…'
                  : 'خلاصهٔ کار انجام‌شده در این نوبت، اصلاحات انجام‌شده طبق بازخورد استاد…'}
                value={note} onChange={e => setNote(e.target.value)} />
      <div className="row" style={{ marginTop: 8 }}>
        <input type="file" id="practicum-files" multiple
               onChange={e => setFiles([...(e.target.files || [])])} />
        <button className="btn" onClick={submit} disabled={busy}>
          {busy ? 'در حال ارسال…' : internship ? 'ثبت گزارش پیشرفت' : 'ارسال برای ارزیابی استاد'}
        </button>
      </div>
      <div className="hint" style={{ marginTop: 6 }}>
        حداکثر ۵ فایل و هر فایل تا ۱۵ مگابایت (گزارش، پیوست کد، عکس محیط کارآموزی و…).
      </div>
    </div>
  )
}

/* امتیاز طیف لیکرت استاد روی یک گزارش پیشرفت (۰ تا ۴) */
export function LikertScorer({ sub, rec, onDone }) {
  const [draft, setDraft] = useState({ score: '', feedback: '' })
  const [busy, setBusy] = useState(false)

  const save = async () => {
    if (draft.score === '') return alert('امتیاز طیف لیکرت (۰ تا ۴) را انتخاب کنید')
    setBusy(true)
    try {
      await api(`/practicum/submissions/${sub.id}/likert`, { method: 'POST', body: {
        score: Number(draft.score), feedback: draft.feedback } })
      onDone()
    } catch (e) { alert(e.message) } finally { setBusy(false) }
  }

  return (
    <div style={{ marginTop: 6, borderTop: '1px dashed var(--border)', paddingTop: 6 }}>
      <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
        <select value={draft.score} onChange={e => setDraft({ ...draft, score: e.target.value })} style={{ maxWidth: 200 }}>
          <option value="">— امتیاز طیف لیکرت —</option>
          {LIKERT_LABELS.map((l, i) => <option key={i} value={i}>{l}</option>)}
        </select>
        <input placeholder="بازخورد کوتاه (اختیاری)" style={{ flex: 1, minWidth: 160 }}
               value={draft.feedback} onChange={e => setDraft({ ...draft, feedback: e.target.value })} />
        <button className="btn small" onClick={save} disabled={busy}>
          {busy ? 'در حال ثبت…' : 'ثبت امتیاز'}
        </button>
      </div>
    </div>
  )
}

/* تأیید نهایی کارآموزی — استاد؛ نمره = سرجمع امتیاز لیکرت (سقف ۲۰) */
export function FinalApproveCard({ rec, onDone }) {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const minOk = (rec.round_count || 0) >= (rec.min_reports || 5)
  const allScored = (rec.unscored_count || 0) === 0

  const approve = async () => {
    setBusy(true)
    try {
      await api(`/practicum/${rec.id}/final-approve`, { method: 'POST', body: { supervisor_note: note } })
      onDone()
    } catch (e) { alert(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="card" style={{ borderRight: '4px solid var(--accent)' }}>
      <h4>🏁 تأیید نهایی کارآموزی</h4>
      <div className="hint">
        وقتی کار شما با دانشجو تمام شد، تأیید نهایی را بزنید. نمرهٔ نهایی از سرجمع امتیاز طیف لیکرت
        گزارش‌ها محاسبه می‌شود: <b>امتیاز فعلی {toFa(rec.current_score ?? 0)} — نمرهٔ نهایی از ۲۰</b>
        {' '}(۵ گزارش کامل با امتیاز عالی = نمرهٔ ۲۰).
      </div>
      <ul style={{ margin: '6px 0', paddingRight: 18, fontSize: 13 }}>
        <li>{minOk ? '✅' : '⬜'} حداقل گزارش‌ها: {toFa(rec.round_count)} از {toFa(rec.min_reports || 5)}</li>
        <li>{allScored ? '✅' : '⬜'} امتیاز همهٔ گزارش‌ها ثبت شده
          {(rec.unscored_count || 0) > 0 && ` — ${toFa(rec.unscored_count)} گزارش بدون امتیاز`}</li>
      </ul>
      <textarea rows={2} placeholder="جمع‌بندی استاد (اختیاری)…" value={note} onChange={e => setNote(e.target.value)} />
      <div className="row" style={{ marginTop: 8 }}>
        <button className="btn" onClick={approve} disabled={busy || !minOk || !allScored}
                title={(!minOk || !allScored) ? 'ابتدا شرط‌های بالا را کامل کنید' : ''}>
          {busy ? 'در حال ثبت…' : '✅ تأیید نهایی کارآموزی'}
        </button>
      </div>
      <div className="hint" style={{ marginTop: 6 }}>
        پس از تأیید، این کارآموزی در «گزارش کارآموزی‌ها» برای مدیرآموزش/مدیرگروه با نمرهٔ نهایی ثبت می‌شود.
      </div>
    </div>
  )
}

/* نمای کامل رکورد — درس‌پروژه/تحقیق و ارائه با چرخهٔ نوبت‌ها؛ کارآموزی با گردش پذیرش/لیکرت/تأیید نهایی */
export function RecordDetail({ id, onBack, user }) {
  const [rec, setRec] = useState(null)
  const [review, setReview] = useState({ feedback: '', score: '' })

  const load = () => api(`/practicum/${id}`).then(setRec).catch(e => alert(e.message))
  useEffect(() => { load() }, [id])
  if (!rec) return <div className="card hint">در حال بارگذاری…</div>

  const isOwner = user.id === rec.student_id
  const isSupervisor = user.id === rec.supervisor_id
  const isInternship = rec.course_type === 'internship'
  const openRound = rec.submissions.find(s => s.status === 'pending')
  const flow = isInternship
    ? [
        ['ثبت کارآموزی', true],
        ['پذیرش و زمان‌بندی استاد', !!rec.accepted_at],
        ['گزارش‌های پیشرفت', (rec.round_count || 0) > 0],
        ['تأیید نهایی', rec.status === 'approved'],
      ]
    : [
        ['ارسال گزارش', rec.round_count > 0],
        ['ارزیابی استاد', rec.submissions.some(s => s.status !== 'pending')],
        ['اصلاح و نوبت بعد', rec.submissions.some(s => s.status === 'needs_revision')],
        ['تأیید نهایی', rec.status === 'approved'],
      ]

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
          {rec.semester ? ` · ${rec.semester}` : ''} · گزارش‌های ثبت‌شده: {toFa(rec.round_count)}
          {isInternship && rec.accepted_at && <> · زمان‌بندی: <b>{INTERVAL_FA[rec.report_interval] || 'هفتگی'}</b> از {fmtDateTime(rec.accepted_at)}</>}
          {isInternship && rec.accepted_at && <> · امتیاز تجمعی: <b>{toFa(rec.current_score ?? 0)}</b> از سقف ۲۰</>}
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

      {/* کارآموزی — پذیرش/زمان‌بندی توسط استاد */}
      {isInternship && isSupervisor && (rec.status === 'pending_acceptance' || rec.status === 'active')
        && <AcceptCard rec={rec} onChanged={load} />}

      {/* کارآموزی — در انتظار پذیرش استاد */}
      {isInternship && rec.status === 'pending_acceptance' && (
        <div className="card">
          <h4>⏳ در انتظار پذیرش استاد مربوطه</h4>
          <div className="hint">
            پس از پذیرش استاد و تعیین زمان‌بندی (روزانه، هفتگی یا دوهفته‌یکبار)، ارسال گزارش پیشرفت از
            همان تاریخ آغاز می‌شود. اعلان پذیرش برای شما ارسال خواهد شد.
          </div>
        </div>
      )}

      {/* فرم گزارش پیشرفت — دانشجو */}
      {isOwner && (rec.status === 'active' || (!isInternship && rec.status !== 'approved' && rec.status !== 'cancelled')) && (
        <SubmissionForm rec={rec} onDone={load} internship={isInternship} />
      )}

      {/* تأیید نهایی کارآموزی — استاد */}
      {isInternship && isSupervisor && rec.status === 'active' && <FinalApproveCard rec={rec} onDone={load} />}

      {/* ارزیابی نوبت — استاد مربوطه (فقط درس‌پروژه/تحقیق و ارائه) */}
      {!isInternship && isSupervisor && openRound && (
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

      {/* تایم‌لاین گزارش‌ها */}
      <div className="card">
        <h4>{isInternship ? `📔 گزارش‌های پیشرفت (${toFa(rec.submissions.length)})` : `🕰️ چرخهٔ ارسال و بازخورد (${toFa(rec.submissions.length)} نوبت)`}</h4>
        <div className="rounds">
          {rec.submissions.map(s => (
            <div key={s.id} className="round-item">
              <div className="round-head">
                <b>{isInternship ? `گزارش پیشرفت ${toFa(s.round_no)}` : `نوبت ${toFa(s.round_no)}`}</b>
                {isInternship ? (
                  s.likert_score != null
                    ? <span className="badge green">امتیاز لیکرت: {toFa(s.likert_score)} از ۴</span>
                    : <span className="badge amber">در انتظار امتیاز استاد</span>
                ) : (
                  <span className={`badge ${s.status === 'approved' ? 'green' : s.status === 'needs_revision' ? 'red' : 'amber'}`}>{s.status_fa}</span>
                )}
                <span className="hint">{fmtDateTime(s.created_at)}</span>
                {!isInternship && s.score != null && <span className="badge teal">نمرهٔ نوبت: {toFa(s.score)}</span>}
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
              {s.feedback && (
                <div className="feedback-box">
                  <b style={{ color: isInternship || s.status === 'approved' ? 'var(--success)' : 'var(--warn)' }}>
                    {isInternship ? '💬 بازخورد استاد:' : s.status === 'approved' ? '✅ بازخورد استاد (تأیید):' : '↩️ بازخورد استاد (اصلاح لازم):'}
                  </b> {s.feedback}
                  {!isInternship && s.supervisor_note && <div className="hint" style={{ marginTop: 4 }}>توضیح تکمیلی: {s.supervisor_note}</div>}
                  <div className="hint" style={{ marginTop: 2 }}>{fmtDateTime(s.reviewed_at)}</div>
                </div>
              )}
              {isInternship && isSupervisor && s.likert_score == null && rec.status === 'active'
                && <LikertScorer sub={s} rec={rec} onDone={load} />}
            </div>
          ))}
          {rec.submissions.length === 0 && (
            <div className="empty">{isInternship ? 'هنوز گزارش پیشرفتی ثبت نشده است.' : 'هنوز نوبتی ارسال نشده است.'}</div>
          )}
        </div>
      </div>
    </>
  )
}
