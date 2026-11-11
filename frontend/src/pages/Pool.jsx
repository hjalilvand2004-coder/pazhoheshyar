import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, REQ_STATUS, STATUS_BADGE, fmtDateTime, toFa } from '../api.js'

// رنگ اختصاصی هر وضعیت — برای نوار بالای کارت، نقطه تایم‌لاین و نمودار حلقه‌ای
const STATUS_COLOR = {
  published: '#0d9488',
  offers_received: '#d97706',
  negotiating: '#7c3aed',
  initial_agreement: '#0f766e',
  pending_university_approval: '#d97706',
  connected_to_project: '#16a34a',
}
const STATUS_ICON = { published: '🌊', offers_received: '📨', negotiating: '💬' }

const VIEWS = [
  { key: 'cards', label: 'نمای کارت', icon: '▦' },
  { key: 'timeline', label: 'نمای تایم‌لاین', icon: '⏳' },
  { key: 'table', label: 'نمای جدولی', icon: '☰' },
]

function Donut({ counts, total }) {
  const entries = Object.entries(counts)
  let acc = 0
  const segs = entries.map(([k, v]) => {
    const start = acc
    acc += (v / Math.max(total, 1)) * 360
    return `${STATUS_COLOR[k] || '#94a3b8'} ${start}deg ${acc}deg`
  })
  return (
    <div className="donut" style={{ background: entries.length ? `conic-gradient(${segs.join(',')})` : '#e2e8f0' }}>
      <div className="donut-hole"><b>{toFa(total)}</b><span>درخواست فعال</span></div>
    </div>
  )
}

export default function Pool() {
  const [items, setItems] = useState([])
  const [q, setQ] = useState('')
  const [field, setField] = useState('')
  const [skill, setSkill] = useState('')
  const [statusF, setStatusF] = useState('')
  const [view, setView] = useState(() => localStorage.getItem('pool_view') || 'cards')
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => { localStorage.setItem('pool_view', view) }, [view])

  const load = () => {
    setLoading(true)
    const p = new URLSearchParams()
    if (q) p.set('q', q)
    if (field) p.set('field', field)
    if (skill) p.set('skill', skill)
    api(`/requests/pool?${p}`)
      .then(setItems)
      .catch(e => setErr(e.message))
      .finally(() => setLoading(false))
  }
  useEffect(load, [q, field, skill])

  const counts = useMemo(() => {
    const c = {}
    for (const r of items) c[r.status] = (c[r.status] || 0) + 1
    return c
  }, [items])

  const filtered = statusF ? items.filter(r => r.status === statusF) : items

  const resetFilters = () => { setQ(''); setField(''); setSkill(''); setStatusF('') }

  return (
    <>
      {err && <div className="error-box">{err}</div>}

      <div className="pool-hero">
        <div className="pool-hero-in">
          <div className="icon-big">🌊</div>
          <div>
            <h2>استخر پژوهشی</h2>
            <p>درخواست‌های منتشرشده دانشجویان که طبق دامنه‌بندی برای شما قابل مشاهده‌اند. با «اعلام آمادگی» وارد فرایند گفت‌وگو شوید و تیم پژوهشی خود را بسازید.</p>
          </div>
        </div>
      </div>

      <div className="stats-strip">
        <div className="stat-tile"><div className="ic" style={{ background: '#e0f2fe' }}>🗂️</div><div><div className="num">{toFa(items.length)}</div><div className="lbl">کل درخواست‌های استخر</div></div></div>
        <div className="stat-tile"><div className="ic">🌊</div><div><div className="num">{toFa(counts.published || 0)}</div><div className="lbl">منتشرشده در استخر</div></div></div>
        <div className="stat-tile"><div className="ic" style={{ background: '#fef3c7' }}>📨</div><div><div className="num">{toFa(counts.offers_received || 0)}</div><div className="lbl">دریافت پیشنهاد</div></div></div>
        <div className="stat-tile"><div className="ic" style={{ background: '#ede9fe' }}>💬</div><div><div className="num">{toFa(counts.negotiating || 0)}</div><div className="lbl">در حال مذاکره</div></div></div>
      </div>

      <div className="donut-wrap">
        <Donut counts={counts} total={items.length} />
        <div className="legend">
          {Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
            <div className="li" key={k}>
              <span className="dot" style={{ background: STATUS_COLOR[k] || '#94a3b8' }} />
              <span>{STATUS_ICON[k] || '•'} {REQ_STATUS[k] || k}</span>
              <span className="n">{toFa(v)}</span>
              <div className="bar"><div style={{ width: `${(v / Math.max(items.length, 1)) * 100}%`, background: STATUS_COLOR[k] || '#94a3b8' }} /></div>
            </div>
          ))}
          {items.length === 0 && <div className="hint">هنوز داده‌ای برای نمودار نیست.</div>}
        </div>
        <div className="seg" style={{ marginInlineStart: 'auto' }}>
          {VIEWS.map(v => (
            <button key={v.key} className={view === v.key ? 'active' : ''} onClick={() => setView(v.key)}>
              {v.icon} {v.label}
            </button>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="row">
          <input placeholder="جست‌وجو در عنوان و خلاصه…" value={q} onChange={e => setQ(e.target.value)} />
          <input placeholder="حوزه (مثال: هوش مصنوعی)" value={field} onChange={e => setField(e.target.value)} />
          <input placeholder="مهارت (مثال: پایتون)" value={skill} onChange={e => setSkill(e.target.value)} />
        </div>
        <div className="chips">
          <button className={`fchip ${!statusF ? 'active' : ''}`} onClick={() => setStatusF('')}>همه <span className="c">{toFa(items.length)}</span></button>
          {Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
            <button key={k} className={`fchip ${statusF === k ? 'active' : ''}`} onClick={() => setStatusF(statusF === k ? '' : k)}>
              {STATUS_ICON[k] || '•'} {REQ_STATUS[k] || k} <span className="c">{toFa(v)}</span>
            </button>
          ))}
        </div>
      </div>

      {loading && <div className="fancy-empty"><div className="big">⏳</div>در حال دریافت درخواست‌های استخر…</div>}

      {!loading && view === 'cards' && (
        <div className="pool-grid">
          {filtered.map(r => (
            <div className="pcard" key={r.id} style={{ '--bar': STATUS_COLOR[r.status] || '#94a3b8' }}>
              <div className="top">
                <span className={`badge ${STATUS_BADGE[r.status]}`}>{REQ_STATUS[r.status]}</span>
                {r.field && <span className="field-chip">📍 {r.field}</span>}
              </div>
              <div className="title"><Link to={`/requests/${r.id}`}>{r.title}</Link></div>
              <div className="clamp2">{r.summary || (r.problem || '').slice(0, 170) || 'خلاصه‌ای ثبت نشده است.'}</div>
              {r.skills?.length > 0 && (
                <div className="skill-chips">
                  {r.skills.slice(0, 6).map(s => <span className="skill-chip" key={s}>{s}</span>)}
                  {r.skills.length > 6 && <span className="skill-chip">+{toFa(r.skills.length - 6)}</span>}
                </div>
              )}
              <div className="meta">
                <span>👤 {r.student_name}</span>
                <span>🕐 {fmtDateTime(r.updated_at)}</span>
                {r.timeline && <span>⏱️ {r.timeline}</span>}
              </div>
              <Link className="btn small" to={`/requests/${r.id}`}>مشاهده و اعلام آمادگی ←</Link>
            </div>
          ))}
        </div>
      )}

      {!loading && view === 'timeline' && (
        <div className="tl">
          {filtered.map(r => (
            <div className="tl-item" key={r.id} style={{ '--dot': STATUS_COLOR[r.status] || '#94a3b8' }}>
              <div className="row" style={{ gap: 8 }}>
                <span className={`badge ${STATUS_BADGE[r.status]}`}>{REQ_STATUS[r.status]}</span>
                <b style={{ flex: 2, minWidth: 200 }}><Link to={`/requests/${r.id}`}>{r.title}</Link></b>
                {r.field && <span className="field-chip">📍 {r.field}</span>}
              </div>
              <div className="hint" style={{ marginTop: 5 }}>
                👤 {r.student_name} • 🕐 {fmtDateTime(r.updated_at)}{r.skills?.length ? ` • مهارت‌ها: ${r.skills.join('، ')}` : ''}
              </div>
              <div style={{ marginTop: 8 }}><Link className="btn small secondary" to={`/requests/${r.id}`}>مشاهده و اعلام آمادگی</Link></div>
            </div>
          ))}
        </div>
      )}

      {!loading && view === 'table' && (
        <div className="card" style={{ overflowX: 'auto' }}>
          <table className="tbl">
            <thead>
              <tr><th>عنوان</th><th>وضعیت</th><th>حوزه</th><th>مهارت‌ها</th><th>دانشجو</th><th>آخرین به‌روزرسانی</th><th></th></tr>
            </thead>
            <tbody>
              {filtered.map(r => (
                <tr key={r.id}>
                  <td style={{ maxWidth: 280 }}><Link to={`/requests/${r.id}`}><b>{r.title}</b></Link></td>
                  <td><span className={`badge ${STATUS_BADGE[r.status]}`}>{REQ_STATUS[r.status]}</span></td>
                  <td>{r.field || '—'}</td>
                  <td style={{ maxWidth: 180 }}>{r.skills?.join('، ') || '—'}</td>
                  <td>{r.student_name}</td>
                  <td className="hint" style={{ whiteSpace: 'nowrap' }}>{fmtDateTime(r.updated_at)}</td>
                  <td><Link className="btn small secondary" to={`/requests/${r.id}`}>مشاهده</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loading && filtered.length === 0 && (
        <div className="fancy-empty">
          <div className="big">🌊</div>
          <b>درخواستی برای نمایش یافت نشد.</b>
          <div className="hint" style={{ marginTop: 4 }}>فیلترها را تغییر دهید یا بعداً سر بزنید — درخواست‌های جدید دانشجویان اینجا ظاهر می‌شوند.</div>
          <button className="btn secondary small" style={{ marginTop: 10 }} onClick={resetFilters}>پاک‌کردن همه فیلترها</button>
        </div>
      )}
    </>
  )
}
