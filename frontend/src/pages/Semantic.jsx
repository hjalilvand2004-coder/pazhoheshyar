import React, { useEffect, useMemo, useState } from 'react'
import { api, fmtDate } from '../api.js'

/* شبکهٔ دانش و لایه معنایی — سطح مشترک سامانه، نه بخش جدا:
   جست‌وجوی ترکیبی، موجودیت با منشأ، مسیرهای مجاز، واژگان و پیشنهادهای توجیه‌دار */

const ORIGIN_STYLE = {
  asserted: { cls: 'badge green', fa: 'رسمی' },
  extracted: { cls: 'badge amber', fa: 'استخراج‌شده' },
  inferred: { cls: 'badge teal', fa: 'استنتاجی' },
}
const POLICY_FA = { public: 'عمومی', internal: 'داخلی', restricted: 'محدود' }
const KIND_ICONS = {
  Person: '👤', Organization: '🏛️', AcademicUnit: '🏛️', Skill: '🛠️', Concept: '💡',
  Topic: '📚', ResearchRequest: '📝', ResearchProject: '🗂️', Publication: '📄',
}

function OriginBadge({ origin }) {
  const o = ORIGIN_STYLE[origin] || { cls: 'badge gray', fa: origin }
  return <span className={o.cls}>{o.fa}</span>
}

function EntityChip({ e, onPick }) {
  return (
    <button className="fchip" onClick={() => onPick(e.id)} title={e.kind_fa}>
      <span>{e.name}</span>
      <span className="c">{e.kind_fa}</span>
    </button>
  )
}

export default function Semantic() {
  const [overview, setOverview] = useState(null)
  const [q, setQ] = useState('')
  const [results, setResults] = useState(null)
  const [entity, setEntity] = useState(null)
  const [nb, setNb] = useState(null)
  const [nbDepth, setNbDepth] = useState(1)
  const [prov, setProv] = useState(null)
  const [cQ, setCQ] = useState('')
  const [concepts, setConcepts] = useState(null)
  const [topic, setTopic] = useState('')
  const [recs, setRecs] = useState(null)
  const [collab, setCollab] = useState(null)
  const [pathSrc, setPathSrc] = useState('')
  const [pathDst, setPathDst] = useState('')
  const [paths, setPaths] = useState(null)
  const [err, setErr] = useState('')

  const loadOverview = () => api('/semantic/graph/overview').then(setOverview).catch(e => setErr(e.message))
  useEffect(() => { loadOverview(); api('/semantic/recommendations/collaborations').then(setCollab).catch(() => {}) }, [])

  const doSearch = async (query = q) => {
    setErr('')
    try {
      const r = await api(`/semantic/search?q=${encodeURIComponent(query)}`)
      setResults(r)
    } catch (e) { setErr(e.message) }
  }

  const pick = async (eid) => {
    setErr(''); setProv(null); setPaths(null)
    try {
      const e = await api(`/semantic/entities/${eid}`)
      setEntity(e)
      const n = await api(`/semantic/entities/${eid}/neighborhood?depth=${nbDepth}&limit=30`)
      setNb(n)
    } catch (e2) { setErr(e2.message) }
  }

  useEffect(() => {
    if (entity) api(`/semantic/entities/${entity.id}/neighborhood?depth=${nbDepth}&limit=30`).then(setNb).catch(() => {})
  }, [nbDepth]) // eslint-disable-line

  const loadProv = async () => {
    try { setProv(await api(`/semantic/entities/${entity.id}/provenance`)) } catch (e) { setErr(e.message) }
  }
  const loadConcepts = async (qq = cQ) => {
    try { setConcepts(await api(`/semantic/concepts?q=${encodeURIComponent(qq)}`)) } catch (e) { setErr(e.message) }
  }
  const recommend = async () => {
    setErr(''); setRecs(null)
    try { setRecs(await api('/semantic/recommendations/supervisors', { method: 'POST', body: { topic_text: topic } })) }
    catch (e) { setErr(e.message) }
  }
  const findPaths = async () => {
    setErr(''); setPaths(null)
    if (!pathSrc || !pathDst) { setErr('دو موجودیت را انتخاب کنید'); return }
    try { setPaths(await api('/semantic/path-queries', { method: 'POST', body: { source_eid: pathSrc, target_eid: pathDst, max_hops: 4 } })) }
    catch (e) { setErr(e.message) }
  }

  const kindList = useMemo(() => {
    if (!overview) return []
    return Object.entries(overview.kinds || {}).map(([k, n]) => ({ k, n, fa: (overview.kind_labels || {})[k] || k }))
  }, [overview])

  return (
    <>
      <div className="pool-hero">
        <span className="deco d1">🕸️</span>
        <span className="deco d2">🧠</span>
        <div className="pool-hero-in">
          <div className="icon-big">🧠</div>
          <div>
            <h2>شبکهٔ دانش و لایه معنایی</h2>
            <p>
              تصویر یکپارچه و نسخه‌دار از موجودیت‌ها و پیوندهای سامانه؛ هر پاسخ می‌گوید بر اساس کدام منبع،
              با چه اعتباری و در چه بازهٔ زمانی است. روابط «استنتاجی» پیشنهاد الگوریتم‌اند و به معنای تخصص
              تأییدشده یا همکاری واقعی نیستند.
            </p>
          </div>
        </div>
      </div>

      {err && <div className="error-box">{err}</div>}

      {overview && (
        <div className="stats-strip">
          <div className="stat-tile"><div className="ic">🧩</div><div><div className="num">{Object.values(overview.kinds || {}).reduce((a, b) => a + b, 0)}</div><div className="lbl">موجودیت در شبکه</div></div></div>
          <div className="stat-tile"><div className="ic">🔗</div><div><div className="num">{overview.visible_claims}</div><div className="lbl">پیوند مجازِ قابل مشاهده</div></div></div>
          {kindList.slice(0, 4).map(x => (
            <div className="stat-tile" key={x.k}><div className="ic">{KIND_ICONS[x.k] || '·'}</div><div><div className="num">{x.n}</div><div className="lbl">{x.fa}</div></div></div>
          ))}
        </div>
      )}

      <div className="card">
        <h3>🔎 جست‌وجوی معنایی دانشگاه</h3>
        <div className="row">
          <input placeholder="مثلاً: استاد پردازش تصویر — یا student1 — یا پردازش تصویر پزشکی" value={q}
                 onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && doSearch()} />
          <button className="btn" onClick={() => doSearch()}>جست‌وجو</button>
        </div>
        {results && (
          <div style={{ marginTop: 12 }}>
            {results.results.length === 0 && <div className="empty">نتیجه‌ای در محدودهٔ مجاز شما یافت نشد</div>}
            <div className="tl">
              {results.results.map(r => (
                <div className="tl-item" key={r.id} style={{ cursor: 'pointer' }} onClick={() => pick(r.id)}>
                  <b>{r.name}</b> <span className="field-chip">{r.kind_fa}</span>
                  <div className="hint">
                    {r.reasons?.join(' • ')} — امتیاز {r.score}
                  </div>
                  {r.summary && <div className="clamp2">{r.summary}</div>}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {entity && (
        <div className="card">
          <h3>🧩 موجودیت: {entity.name} <span className="field-chip">{entity.kind_fa}</span></h3>
          <div className="row">
            <button className="btn small secondary" onClick={() => setNbDepth(nbDepth === 1 ? 2 : 1)}>
              عمق همسایگی: {nbDepth === 1 ? '۱ گام' : '۲ گام'}
            </button>
            <button className="btn small secondary" onClick={loadProv}>منشأ اطلاعات</button>
            <button className="btn small ghost" onClick={() => { setPathSrc(entity.id); }}>به‌عنوان مبدأ مسیر</button>
            <button className="btn small ghost" onClick={() => { setPathDst(entity.id); }}>به‌عنوان مقصد مسیر</button>
          </div>
          {entity.summary && <p className="hint" style={{ marginTop: 8 }}>{entity.summary}</p>}
          <div style={{ overflowX: 'auto' }}>
            <table className="tbl">
              <thead><tr><th>پیوند</th><th>طرف</th><th>منشأ</th><th>سیاست</th><th>اطمینان</th><th>وضعیت داوری</th></tr></thead>
              <tbody>
                {(entity.relations || []).map(r => (
                  <tr key={r.claim_id}>
                    <td>{r.predicate_fa} {r.direction === 'in' && <span className="hint">(ورودی)</span>}</td>
                    <td><a href="#" onClick={e => { e.preventDefault(); pick(r.other.id) }}>{r.other.name}</a> <span className="field-chip">{r.other.kind_fa}</span></td>
                    <td><OriginBadge origin={r.origin} /></td>
                    <td><span className="badge gray">{POLICY_FA[r.policy] || r.policy}</span></td>
                    <td>{r.confidence != null ? r.confidence : '—'}</td>
                    <td><span className={`badge ${r.review_status === 'approved' ? 'green' : 'amber'}`}>{r.review_status === 'approved' ? 'تأییدشده' : 'در انتظار داوری'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {entity.relations?.length === 0 && <div className="empty">پیوندی در محدودهٔ مجاز شما نیست</div>}

          {nb && (
            <div style={{ marginTop: 14 }}>
              <h3 style={{ fontSize: 14 }}>همسایگی (نمای جدولی)</h3>
              <div className="skill-chips">
                {nb.nodes?.filter(n => n.hops > 0).slice(0, 40).map(n => (
                  <EntityChip key={n.id} e={n} onPick={pick} />
                ))}
              </div>
            </div>
          )}

          {prov && (
            <div style={{ marginTop: 14 }}>
              <h3 style={{ fontSize: 14 }}>منشأ — منبع، نسخه و بازهٔ اعتبار هر ادعا</h3>
              <div className="hint">
                ادعاهای فیلترشده به‌دلیل سیاست دسترسی: {prov.hidden_claims_count} (فقط شمرده می‌شوند، محتوا نمایش داده نمی‌شود)
              </div>
              <div className="skill-chips" style={{ marginTop: 6 }}>
                {prov.claims.slice(0, 12).map(c => (
                  <span className="skill-chip" key={c.claim_id} title={`منبع: ${c.source_system} | نسخه: ${c.rule_or_model_version || '—'}`}>
                    {c.predicate_fa} <b>·</b> {c.origin_fa} <b>·</b> {c.source_system}
                    {c.rule_or_model_version ? <span> · نسخه {c.rule_or_model_version}</span> : null}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="card">
        <h3>🛤️ مسیر مجاز بین دو موجودیت</h3>
        <div className="row">
          <input placeholder="شناسهٔ مبدأ" value={pathSrc} onChange={e => setPathSrc(e.target.value)} />
          <input placeholder="شناسهٔ مقصد" value={pathDst} onChange={e => setPathDst(e.target.value)} />
          <button className="btn" onClick={findPaths}>یافتن مسیر</button>
        </div>
        {paths && paths.paths.length === 0 && <div className="empty">مسیر مجازی یافت نشد (یا دادهٔ حساس در مسیر است)</div>}
        {paths?.paths.map((p, i) => (
          <div className="ok-box" key={i}>
            {p.steps.map((s, j) => (
              <span key={j}>
                <b>{s.pred_fa}</b> ← <a href="#" onClick={e => { e.preventDefault(); pick(s.node.id) }}>{s.node.name}</a>
                {' '}<OriginBadge origin={s.origin} />{' '}
              </span>
            ))}
          </div>
        ))}
      </div>

      <div className="card">
        <h3>🎓 پیشنهاد استاد راهنما (توجیه‌دار و آگاه از شروط رسمی)</h3>
        <div className="row">
          <input placeholder="موضوع پیشنهادی پژوهش؛ مثلاً: تشخیص بیماری با یادگیری عمیق روی تصاویر پزشکی"
                 value={topic} onChange={e => setTopic(e.target.value)} />
          <button className="btn" onClick={recommend}>پیشنهاد بگیر</button>
        </div>
        {recs && (
          <div style={{ marginTop: 12 }}>
            <div className="demo-banner">
              نسخهٔ الگوریتم: {recs.algorithm_version} — {recs.note}
            </div>
            {recs.candidates.length === 0 && <div className="empty">کاندیدایی با شواهد کافی یافت نشد</div>}
            {recs.candidates.map(c => (
              <div className="tl-item" key={c.user_id}>
                <b>{c.name}</b> <span className="field-chip">{c.faculty || '—'}</span>
                <span className={`badge ${c.capacity_status === 'known' ? 'green' : 'amber'}`}>
                  {c.capacity_status === 'known' ? `ظرفیت باقی‌مانده: ${c.capacity}` : 'ظرفیت: نامشخص'}
                </span>
                <div className="hint">امتیاز تناسب: {c.score} — اجزا: مفهومی {c.components.concept}، مهارتی {c.components.skill}، گراف {c.components.graph}</div>
                <div className="clamp2">{c.explanation}</div>
                {c.shared_concepts?.length > 0 && (
                  <div className="skill-chips" style={{ marginTop: 6 }}>
                    {c.shared_concepts.map(s => <span className="skill-chip" key={s}>{s}</span>)}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {collab && collab.candidates?.length > 0 && (
        <div className="card">
          <h3>🤝 نامزدهای همکاری استنتاجی</h3>
          <div className="demo-banner">نسخهٔ {collab.version} — {collab.note}</div>
          {collab.candidates.slice(0, 6).map((c, i) => (
            <div className="tl-item" key={i}>
              <b>{c.name}</b> <span className="badge teal">اطمینان {c.confidence}</span>
              {c.shared_concepts?.length > 0 && <div className="hint">مفاهیم مشترک: {c.shared_concepts.join('، ')}</div>}
            </div>
          ))}
        </div>
      )}

      <div className="card">
        <h3>📖 واژگان کنترل‌شده (SKOS-سازگار)</h3>
        <div className="row">
          <input placeholder="جست‌وجوی مفهوم یا مترادف؛ مثلاً ML" value={cQ}
                 onChange={e => setCQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && loadConcepts()} />
          <button className="btn secondary" onClick={() => loadConcepts()}>نمایش واژگان</button>
        </div>
        {concepts && (
          <div style={{ marginTop: 10 }}>
            <div className="hint">نسخهٔ واژگان: {concepts.version} — تعداد: {concepts.total}</div>
            <div className="skill-chips" style={{ marginTop: 6 }}>
              {concepts.concepts.map(c => (
                <span className="skill-chip" key={c.id} title={c.definition}>
                  {c.name_fa}{c.name_en ? ` / ${c.name_en}` : ''}
                  {c.synonyms?.length ? ` (≈ ${c.synonyms.join('، ')})` : ''}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  )
}
