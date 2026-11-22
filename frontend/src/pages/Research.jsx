import React, { useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api, fmtDateTime, toFa } from '../api.js'

const DOC_STATUSES = {
  draft: 'پیش‌نویس', in_review: 'در حال داوری داخلی', revised: 'بازنویسی‌شده',
  approved: 'تأیید مسئول سند', published: 'منتشرشده در شبکهٔ دانش',
}
const DOC_FLOW = ['draft', 'in_review', 'revised', 'approved', 'published']
const ROLE_LABEL = { lead: 'مسئول', writer: 'نویسنده', reviewer: 'داور', observer: 'ناظر' }

async function downloadFile(path, filename) {
  const { getToken } = await import('../api.js')
  const res = await fetch('/api/v1' + path, { headers: { Authorization: `Bearer ${getToken()}` } })
  if (!res.ok) { alert('خطا در تولید خروجی'); return }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

const DEMO_BANNER = (
  <div className="demo-banner">
    <b>🤝 فضای پژوهش تیمی:</b> نگارش مشترک سند با نقش‌ها، نسخه‌ها و داوری داخلی — دستیار نگارش قاعده‌محور است و
    جای بازنویسی انسانی را نگه می‌دارد. انتشار نهایی، سند را به‌عنوان «اثر علمی» در شبکهٔ دانش ثبت می‌کند.
  </div>
)

export default function Research() {
  const { id } = useParams()
  const nav = useNavigate()
  const [templates, setTemplates] = useState([])
  const [docs, setDocs] = useState([])
  const [projects, setProjects] = useState([])
  const [creating, setCreating] = useState(false)
  const [draft, setDraft] = useState({ title: '', template: 'ieee-conference', venue_note: '', project_id: '' })

  useEffect(() => {
    api('/research/templates').then(setTemplates).catch(() => {})
    api('/research/docs/mine').then(setDocs).catch(() => {})
    api('/projects/mine').then(p => setProjects(p)).catch(() => {})
  }, [])

  const create = async () => {
    if (!draft.title.trim()) return alert('عنوان سند را بنویسید')
    try {
      const d = await api('/research/docs', { method: 'POST', body: {
        ...draft, project_id: draft.project_id || null } })
      setCreating(false)
      setDraft({ title: '', template: draft.template, venue_note: '', project_id: '' })
      nav(`/research/${d.id}`)
    } catch (e) { alert(e.message) }
  }

  if (id) return <DocView id={id} templates={templates} />
  return (
    <>
      <div className="card">
        <h3>📝 فضای پژوهش — نگارش مشترک مقاله و مستند پژوهشی</h3>
        {DEMO_BANNER}
        <p className="hint" style={{ marginTop: 8 }}>
          سند را با قالب استاندارد (IEEE، اسپرینگر، APA، پایان‌نامهٔ فارسی) بسازید؛ اعضای گروه با نقش نویسنده/داور
          بخش‌ها را می‌نویسند، نسخه ثبت می‌شود و خروجی نهایی در همان قالب تولید می‌گردد.
        </p>
        <button className="btn" onClick={() => setCreating(v => !v)}>{creating ? 'بستن فرم' : '＋ سند پژوهشی جدید'}</button>
        {creating && (
          <div style={{ marginTop: 10, display: 'grid', gap: 8 }}>
            <input placeholder="عنوان مقاله/مستند پژوهشی" value={draft.title}
                   onChange={e => setDraft({ ...draft, title: e.target.value })} />
            <div className="grid cols-2">
              <select value={draft.template} onChange={e => setDraft({ ...draft, template: e.target.value })}>
                {templates.map(t => <option key={t.key} value={t.key}>{t.title}</option>)}
              </select>
              <select value={draft.project_id} onChange={e => setDraft({ ...draft, project_id: e.target.value })}>
                <option value="">— بدون پیوند به پروژه —</option>
                {projects.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}
              </select>
            </div>
            <input placeholder="مقصد ارسال (اختیاری): نام کنفرانس یا مجله" value={draft.venue_note}
                   onChange={e => setDraft({ ...draft, venue_note: e.target.value })} />
            <button className="btn" onClick={create}>ایجاد سند با اسکلت قالب</button>
          </div>
        )}
      </div>

      <div className="grid cols-2">
        {docs.map(d => (
          <div key={d.id} className="card" style={{ cursor: 'pointer' }} onClick={() => nav(`/research/${d.id}`)}>
            <h4>{d.title}</h4>
            <div className="hint">{d.template_title} · {d.status_fa} · {toFa(d.member_count)} عضو</div>
            {d.venue_note && <div className="hint">مقصد: {d.venue_note}</div>}
          </div>
        ))}
        {docs.length === 0 && <div className="card hint">هنوز سند پژوهشی ندارید — از دکمهٔ بالا یکی بسازید.</div>}
      </div>
    </>
  )
}

function DocView({ id, templates }) {
  const [doc, setDoc] = useState(null)
  const [err, setErr] = useState('')
  const [tab, setTab] = useState('ai')
  const load = async () => {
    try { setDoc(await api(`/research/docs/${id}`)) } catch (e) { setErr(e.message) }
  }
  useEffect(() => { load() }, [id])

  if (err) return <div className="card">⛔ {err}</div>
  if (!doc) return <div className="card hint">در حال بارگذاری…</div>
  const myRole = doc.my_role
  const isLead = myRole === 'lead'
  return (
    <>
      <div className="card">
        <h3>{doc.title}</h3>
        <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
          {DOC_FLOW.map(st => (
            <span key={st} className="badge" style={{
              background: doc.status === st ? 'var(--primary)' : 'transparent',
              color: doc.status === st ? '#fff' : 'var(--muted)',
              border: '1px solid var(--primary)', borderRadius: 999, padding: '2px 10px', fontSize: 11 }}>
              {DOC_STATUSES[st]}
            </span>
          ))}
        </div>
        <div className="hint" style={{ marginTop: 6 }}>
          قالب: {doc.template_title} · نقش من: {ROLE_LABEL[myRole] || '—'} · مسئول: {doc.owner_name}
          {doc.semantic_entity_id && <> · 🕸️ ثبت‌شده در شبکهٔ دانش</>}
        </div>
        <Actions doc={doc} myRole={myRole} reload={load} />
      </div>
      <Sections doc={doc} myRole={myRole} reload={load} />
      <div className="card">
        <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
          {[['ai', '🤖 دستیار نگارش'], ['members', '👥 اعضا'], ['refs', '📚 مرجع‌ها'],
            ['versions', '🕘 نسخه‌ها'], ['comments', '💬 گفت‌وگوی داوری'], ['export', '📤 خروجی قالب']].map(([k, l]) => (
            <button key={k} className={`btn small ${tab === k ? '' : 'ghost'}`} onClick={() => setTab(k)}>{l}</button>
          ))}
        </div>
      </div>
      {tab === 'ai' && <AiPanel doc={doc} reload={load} />}
      {tab === 'members' && <MembersPanel doc={doc} isLead={isLead} reload={load} />}
      {tab === 'refs' && <RefsPanel doc={doc} myRole={myRole} />}
      {tab === 'versions' && <VersionsPanel doc={doc} isLead={isLead} reload={load} />}
      {tab === 'comments' && <CommentsPanel doc={doc} myRole={myRole} reload={load} />}
      {tab === 'export' && <ExportPanel doc={doc} templates={templates} />}
    </>
  )
}

function Actions({ doc, myRole, reload }) {
  const next = { draft: [['submit_review', 'ارسال برای داوری']], in_review: [['mark_revised', 'بازنویسی انجام شد']],
    revised: [['approve', 'تأیید سند (مسئول)']], approved: [['reopen', 'بازگشت به پیش‌نویس']] }
  const act = async (action) => {
    try { await api(`/research/docs/${doc.id}`, { method: 'PATCH', body: { action } }); reload() } catch (e) { alert(e.message) }
  }
  return (
    <div className="row" style={{ gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
      {(next[doc.status] || []).map(([a, l]) => (
        <button key={a} className="btn small" disabled={a === 'approve' && myRole !== 'lead'}
                onClick={() => act(a)}>{l}</button>
      ))}
      {doc.status === 'approved' && myRole === 'lead' && (
        <button className="btn small" onClick={async () => {
          try { const r = await api(`/research/docs/${doc.id}/publish`, { method: 'POST' })
            alert(`در شبکهٔ دانش ثبت شد — نویسندگی: ${toFa(r.authors)} نفر، مفاهیم: ${toFa(r.concepts)}`); reload()
          } catch (e) { alert(e.message) }
        }}>🕸️ انتشار در شبکهٔ دانش</button>
      )}
    </div>
  )
}

function Sections({ doc, myRole, reload }) {
  const writable = ['lead', 'writer'].includes(myRole)
  const [editing, setEditing] = useState({})
  const [busy, setBusy] = useState({})
  const save = async (s) => {
    setBusy(b => ({ ...b, [s.id]: true }))
    try {
      await api(`/research/docs/${doc.id}/sections/${s.id}`, { method: 'PATCH',
        body: { heading: s.heading, body: s.body, base_version_no: s.version_no } })
      setEditing(e => ({ ...e, [s.id]: false }))
      reload()
    } catch (e) {
      if (e.status === 409) alert(e.message.message || 'هم‌زمان ویرایش شده؛ صفحه را دوباره باز کنید')
      else alert(e.message)
    } finally { setBusy(b => ({ ...b, [s.id]: false })) }
  }
  return (
    <>
      {doc.sections.map(s => {
        const words = (s.body || '').trim() ? s.body.trim().split(/\s+/).length : 0
        return (
          <div key={s.id} className="card">
            {editing[s.id] ? (
              <>
                <input value={s.heading} onChange={e => { s.heading = e.target.value; setEditing(v => ({ ...v })) }} />
                <textarea rows={Math.min(14, 4 + Math.floor((s.body || '').length / 90))} style={{ marginTop: 6 }}
                          value={s.body} onChange={e => { s.body = e.target.value; setEditing(v => ({ ...v })) }} />
                <div className="row" style={{ gap: 6, marginTop: 6 }}>
                  <button className="btn small" disabled={busy[s.id]} onClick={() => save(s)}>💾 ذخیره</button>
                  <button className="btn small ghost" onClick={() => { setEditing(v => ({ ...v, [s.id]: false })); reload() }}>انصراف</button>
                  <span className="hint">نسخهٔ سمت شما: {toFa(s.version_no)}</span>
                </div>
              </>
            ) : (
              <>
                <h4>{toFa(s.ord)}. {s.heading}
                  <span className="hint" style={{ fontWeight: 400 }}> — {toFa(words)} واژه
                    {s.assigned_name ? ` · مسئول: ${s.assigned_name}` : ''}</span></h4>
                {s.guidance && !s.body && <div className="hint">💡 {s.guidance}</div>}
                {s.body
                  ? (s.body.split('\n').filter(Boolean).map((p, i) => <p key={i} style={{ margin: '4px 0' }}>{p}</p>))
                  : <div className="hint">— هنوز نوشته نشده —</div>}
                <div className="row" style={{ gap: 6, marginTop: 6 }}>
                  <span className="hint">آخرین ویرایش: {s.updated_name || '—'} · نسخهٔ {toFa(s.version_no)}</span>
                  {writable && <button className="btn small ghost" onClick={() => setEditing(v => ({ ...v, [s.id]: true }))}>✏️ ویرایش</button>}
                </div>
              </>
            )}
          </div>
        )
      })}
      {writable && <AddSection docId={doc.id} reload={reload} />}
    </>
  )
}

function AddSection({ docId, reload }) {
  const [h, setH] = useState('')
  const add = async () => {
    if (!h.trim()) return
    await api(`/research/docs/${docId}/sections`, { method: 'POST', body: { heading: h } }).catch(e => alert(e.message))
    setH(''); reload()
  }
  return (
    <div className="card">
      <div className="row" style={{ gap: 6 }}>
        <input placeholder="عنوان بخش جدید (مثلاً: محدودیت‌های پژوهش)" value={h} onChange={e => setH(e.target.value)} />
        <button className="btn small" onClick={add}>افزودن بخش</button>
      </div>
    </div>
  )
}

function AiPanel({ doc, reload }) {
  const [outline, setOutline] = useState(null)
  const [feedback, setFeedback] = useState(null)
  const [abstract, setAbstract] = useState(null)
  const [keywords, setKeywords] = useState(null)
  const [related, setRelated] = useState(null)
  const call = (set) => (path) => async () => {
    try { set(await api(path, { method: 'POST', body: { doc_id: doc.id } })) } catch (e) { alert(e.message) }
  }
  return (
    <>
      <div className="grid cols-2">
        <div className="card">
          <h4>🗺️ طرح‌وارهٔ نگارش</h4>
          <button className="btn small" onClick={call(setOutline)('/ai/doc-outline')}>تحلیل پیشرفت</button>
          {outline && <div style={{ marginTop: 8 }}>
            <div className="hint">{toFa(outline.progress.filled_sections)}/{toFa(outline.progress.total_sections)} بخش پر شده · {toFa(outline.progress.total_words)} واژه · سبک ارجاع: {outline.citation_style}</div>
            {outline.items.map((it, i) => <div key={i} className="hint">🔹 <b>{it.heading}</b> — {it.suggestion}</div>)}
          </div>}
        </div>
        <div className="card">
          <h4>🔍 بازخورد نگارش</h4>
          <button className="btn small" onClick={call(setFeedback)('/ai/doc-feedback')}>بررسی متن</button>
          {feedback && <div style={{ marginTop: 8 }}>
            <div className="hint">مجموع واژه‌ها: {toFa(feedback.total_words)}</div>
            {feedback.issues.map((f, i) => <div key={i}>⚠️ {f}</div>)}
            {feedback.venue_checklist.length > 0 && <div className="hint">✅ چک‌لیست مقصد: {feedback.venue_checklist.join(' · ')}</div>}
          </div>}
        </div>
        <div className="card">
          <h4>🧩 چکیده‌ساز (استخراجی)</h4>
          <button className="btn small" onClick={call(setAbstract)('/ai/doc-abstract')}>پیش‌نویس چکیده</button>
          {abstract && <div style={{ marginTop: 8 }}>
            {abstract.abstract_draft && <p style={{ background: 'var(--primary-light)', padding: 8, borderRadius: 8 }}>{abstract.abstract_draft}</p>}
            {abstract.abstract_scaffold?.map((s, i) => <div key={i} className="hint">{s}</div>)}
            {abstract.abstract_draft && (
              <button className="btn small" style={{ marginTop: 6 }} onClick={async () => {
                await api(`/research/docs/${doc.id}`, { method: 'PATCH', body: { abstract: abstract.abstract_draft } }).catch(e => alert(e.message))
                reload(); alert('پیش‌نویس در فیلد چکیدهٔ سند ذخیره شد — آن را بازنویسی کنید')
              }}>ذخیره به‌عنوان پیش‌نویس چکیده</button>
            )}
          </div>}
        </div>
        <div className="card">
          <h4>🔑 کلیدواژه و پیشینه</h4>
          <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
            <button className="btn small" onClick={call(setKeywords)('/ai/doc-keywords')}>کلیدواژه‌ها</button>
            <button className="btn small ghost" onClick={call(setRelated)('/ai/doc-related-work')}>اسکلت پیشینه</button>
          </div>
          {keywords && <div style={{ marginTop: 8 }}>
            {keywords.suggestions.map((k, i) => <span key={i} className="badge">{k}</span>)}
            <div className="hint">{keywords.message}</div>
          </div>}
          {related && <div style={{ marginTop: 8 }}>
            {related.scaffold.map((s, i) => <div key={i} className="hint">{s}</div>)}
          </div>}
        </div>
      </div>
      <div className="demo-banner"><b>⚠️</b> خروجی‌های این پنل با موتور قاعده‌محور <b>doc-ai-1.0.0</b> ساخته می‌شوند؛ پیش‌نویس پایه‌اند و جای قضاوت و بازنویسی نویسنده باقی است.</div>
    </>
  )
}

function MembersPanel({ doc, isLead, reload }) {
  const [username, setUsername] = useState('')
  const [role, setRole] = useState('writer')
  const add = async () => {
    try { await api(`/research/docs/${doc.id}/members`, { method: 'POST', body: { username, role } })
      setUsername(''); reload()
    } catch (e) { alert(e.message) }
  }
  const change = async (memberId, r) => {
    await api(`/research/docs/${doc.id}/members/${memberId}`, { method: 'PATCH', body: { role: r } }).catch(e => alert(e.message))
    reload()
  }
  return (
    <div className="card">
      <h4>👥 اعضای تیم نگارش</h4>
      {doc.members.map(m => (
        <div key={m.id} className="row" style={{ gap: 8, padding: '6px 0', borderBottom: '1px dashed #e4eaf2' }}>
          <b>{m.name}</b>
          {isLead && m.role !== 'lead'
            ? <select value={m.role} onChange={e => change(m.id, e.target.value)}>
                {['writer', 'reviewer', 'observer', 'remove'].map(r =>
                  <option key={r} value={r}>{r === 'remove' ? '— حذف از تیم —' : ROLE_LABEL[r]}</option>)}
              </select>
            : <span className="badge">{m.role_fa}</span>}
        </div>
      ))}
      {isLead && (
        <div className="row" style={{ gap: 6, marginTop: 10 }}>
          <input placeholder="نام کاربری (مثلاً student1)" value={username} onChange={e => setUsername(e.target.value)} />
          <select value={role} onChange={e => setRole(e.target.value)}>
            <option value="writer">نویسنده</option><option value="reviewer">داور داخلی</option><option value="observer">ناظر</option>
          </select>
          <button className="btn small" onClick={add}>افزودن عضو</button>
        </div>
      )}
    </div>
  )
}

function RefsPanel({ doc, myRole }) {
  const writable = ['lead', 'writer'].includes(myRole)
  const [form, setForm] = useState({ authors: '', title: '', venue: '', year: '', doi: '', url: '' })
  const [style, setStyle] = useState('ieee')
  const [formatted, setFormatted] = useState([])
  const [refs, setRefs] = useState(doc.references)
  const reload = async () => { const d = await api(`/research/docs/${doc.id}`); setRefs(d.references) }
  const add = async () => {
    try { await api(`/research/docs/${doc.id}/references`, { method: 'POST', body: form })
      setForm({ authors: '', title: '', venue: '', year: '', doi: '', url: '' }); reload()
    } catch (e) { alert(e.message) }
  }
  const fmt = async () => setFormatted((await api(`/research/docs/${doc.id}/references/formatted?style=${style}`)).items)
  return (
    <div className="card">
      <h4>📚 مرجع‌های سند ({toFa(refs.length)})</h4>
      {writable && (
        <div style={{ display: 'grid', gap: 6, margin: '8px 0 14px' }}>
          <input placeholder="نویسندگان (مثلاً: Vahdat, A.; Becker, D.)" value={form.authors}
                 onChange={e => setForm({ ...form, authors: e.target.value })} />
          <input placeholder="عنوان مقاله *" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} />
          <div className="grid cols-2">
            <input placeholder="مجله/کنفرانس" value={form.venue} onChange={e => setForm({ ...form, venue: e.target.value })} />
            <input placeholder="سال" value={form.year} onChange={e => setForm({ ...form, year: e.target.value })} />
          </div>
          <input placeholder="DOI (اختیاری — 10.xxxx/yyyy)" value={form.doi} onChange={e => setForm({ ...form, doi: e.target.value })} />
          <button className="btn small" onClick={add}>افزودن مرجع</button>
        </div>
      )}
      {refs.map(r => (
        <div key={r.id} className="hint" style={{ padding: '5px 0', borderBottom: '1px dashed #e4eaf2' }}>
          📄 {r.authors} — <b>{r.title}</b> {r.venue && <>· {r.venue}</>} {r.year && <>· {toFa(r.year)}</>}
        </div>
      ))}
      {refs.length > 0 && (
        <>
          <div className="row" style={{ gap: 6, marginTop: 12 }}>
            <select value={style} onChange={e => setStyle(e.target.value)}>
              <option value="ieee">سبک IEEE (عددی)</option>
              <option value="springer">سبک اسپرینگر</option>
              <option value="apa">سبک APA</option>
            </select>
            <button className="btn small" onClick={fmt}>فرمت‌بندی مراجع</button>
          </div>
          {formatted.length > 0 && (
            <div style={{ background: 'var(--primary-light)', borderRadius: 10, padding: 10, marginTop: 8 }}>
              {formatted.map(f => <div key={f.id} style={{ direction: 'ltr', textAlign: 'left', fontSize: 12.5, margin: '4px 0' }}>{f.formatted}</div>)}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function VersionsPanel({ doc, isLead, reload }) {
  const [label, setLabel] = useState('')
  const snap = async () => {
    try { await api(`/research/docs/${doc.id}/versions`, { method: 'POST', body: { label } }); setLabel(''); reload()
    } catch (e) { alert(e.message) }
  }
  const restore = async (vid) => {
    if (!confirm('نسخهٔ فعلی بخش‌ها با این عکس فوری جایگزین می‌شود؟')) return
    await api(`/research/docs/${doc.id}/versions/${vid}/restore`, { method: 'POST' }).catch(e => alert(e.message))
    reload()
  }
  return (
    <div className="card">
      <h4>🕘 نسخه‌های سند</h4>
      {['lead', 'writer', 'reviewer'].includes(doc.my_role) && (
        <div className="row" style={{ gap: 6, margin: '8px 0' }}>
          <input placeholder="برچسب نسخه (مثلاً: پیش از ارسال به داور)" value={label} onChange={e => setLabel(e.target.value)} />
          <button className="btn small" onClick={snap}>ثبت نسخهٔ فوری</button>
        </div>
      )}
      {doc.versions.map(v => (
        <div key={v.id} className="row" style={{ gap: 8, padding: '6px 0', borderBottom: '1px dashed #e4eaf2', flexWrap: 'wrap' }}>
          <b>{v.label}</b>
          <span className="hint">{v.created_by} · {fmtDateTime(v.created_at)} · {toFa(v.words)} واژه</span>
          {isLead && <button className="btn small ghost" onClick={() => restore(v.id)}>بازگردانی</button>}
        </div>
      ))}
      {doc.versions.length === 0 && <div className="hint">هنوز نسخه‌ای ثبت نشده است.</div>}
    </div>
  )
}

function CommentsPanel({ doc, myRole, reload }) {
  const [body, setBody] = useState('')
  const [sectionId, setSectionId] = useState('')
  const add = async () => {
    try { await api(`/research/docs/${doc.id}/comments`, { method: 'POST',
      body: { section_id: sectionId ? Number(sectionId) : null, body } })
      setBody(''); setSectionId(''); reload()
    } catch (e) { alert(e.message) }
  }
  const resolve = async (cid) => {
    await api(`/research/docs/${doc.id}/comments/${cid}/resolve`, { method: 'POST' }).catch(e => alert(e.message))
    reload()
  }
  const sName = (sid) => doc.sections.find(s => s.id === sid)?.heading
  return (
    <div className="card">
      <h4>💬 گفت‌وگوی داوری داخلی</h4>
      <div style={{ display: 'grid', gap: 6, margin: '8px 0 14px' }}>
        <select value={sectionId} onChange={e => setSectionId(e.target.value)}>
          <option value="">— دیدگاه کلی روی سند —</option>
          {doc.sections.map(s => <option key={s.id} value={s.id}>{s.heading}</option>)}
        </select>
        <textarea rows={2} placeholder="دیدگاه داوری…" value={body} onChange={e => setBody(e.target.value)} />
        <button className="btn small" onClick={add}>ثبت دیدگاه</button>
      </div>
      {doc.comments.map(c => (
        <div key={c.id} className="row" style={{ gap: 6, padding: '6px 0', borderBottom: '1px dashed #e4eaf2', flexWrap: 'wrap',
             opacity: c.resolved ? 0.6 : 1 }}>
          <b>{c.author}</b>
          <span className="hint">{sName(c.section_id) ? `روی «${sName(c.section_id)}» · ` : ''}{fmtDateTime(c.created_at)}</span>
          <span style={{ width: '100%' }}>{c.body}</span>
          {['lead', 'writer'].includes(myRole) && !c.resolved &&
            <button className="btn small ghost" onClick={() => resolve(c.id)}>✔ حل شد</button>}
        </div>
      ))}
      {doc.comments.length === 0 && <div className="hint">هنوز دیدگاهی ثبت نشده است.</div>}
    </div>
  )
}

function ExportPanel({ doc, templates }) {
  const t = (templates || []).find(x => x.key === doc.template)
  return (
    <div className="card">
      <h4>📤 خروجی در قالب «{doc.template_title}»</h4>
      <div className="hint">{t?.venue_hint}</div>
      <div className="row" style={{ gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
        <button className="btn small" onClick={() => downloadFile(`/research/docs/${doc.id}/export?format=tex`, `research-doc-${doc.id}.tex`)}>-LaTeX (.tex)</button>
        <button className="btn small" onClick={() => downloadFile(`/research/docs/${doc.id}/export?format=html`, `research-doc-${doc.id}.html`)}>HTML چاپ‌آمیز</button>
        <button className="btn small" onClick={() => downloadFile(`/research/docs/${doc.id}/export?format=docx`, `research-doc-${doc.id}.docx`)}>Word (.docx)</button>
      </div>
      <div className="hint" style={{ marginTop: 8 }}>
        فایل tex با کلاس رسمی نشریه ساخته می‌شود (IEEEtran / llncs / XePersian برای فارسی با XeLaTeX)؛
        فایل HTML دوستونه/تک‌ستونهٔ چاپ‌آمیز است و فایل Word با سبک عنوان و فهرست مراجع فرمت‌بندی شده.
      </div>
    </div>
  )
}

