import React, { useEffect, useRef, useState } from 'react'
import { Chart as ChartJS, registerables } from 'chart.js'
import { api, toFa, fmtDateTime } from '../api.js'

ChartJS.register(...registerables)

const PALETTE = ['#2563eb', '#e11d48', '#059669', '#d97706', '#7c3aed', '#0891b2', '#be123c', '#65a30d', '#9333ea', '#0284c7']

function Chart({ type, data, options = {}, height = 260 }) {
  const ref = useRef(null)
  useEffect(() => {
    if (!ref.current || !data) return
    const c = new ChartJS(ref.current, {
      type, data,
      options: { responsive: true, maintainAspectRatio: false, ...options },
    })
    return () => c.destroy()
  }, [type, JSON.stringify(data), JSON.stringify(options)])
  return <div style={{ height, position: 'relative' }}>{data && <canvas ref={ref} />}</div>
}

function Metric({ label, value, hint }) {
  return (
    <div style={{ background: 'var(--primary-light)', borderRadius: 10, padding: '8px 12px', minWidth: 110 }}>
      <div className="hint" style={{ fontSize: 11 }}>{label}</div>
      <b style={{ fontSize: 17 }}>{value ?? '—'}</b>
      {hint && <div className="hint" style={{ fontSize: 10.5 }}>{hint}</div>}
    </div>
  )
}

const heatColor = (r) => {
  if (r === null || r === undefined) return 'transparent'
  const a = Math.min(1, Math.abs(r)) * 0.85 + 0.08
  return r >= 0 ? `rgba(37, 99, 235, ${a})` : `rgba(225, 29, 72, ${a})`
}

export default function Lab() {
  const [tab, setTab] = useState('ds')
  const [meta, setMeta] = useState(null)
  const [list, setList] = useState([])
  const [selected, setSelected] = useState(null)
  const [version, setVersion] = useState(0)   // برای بارگذاری مجدد لیست

  const reload = () => setVersion(v => v + 1)
  useEffect(() => {
    api('/lab/meta').then(setMeta).catch(() => {})
  }, [])
  useEffect(() => {
    api('/lab/datasets').then(setList).catch(() => {})
  }, [version])

  const TABS = [['ds', '🗂️ دیتاست‌ها'], ['explore', '🔍 کاوش و نمودار'], ['simulate', '🧪 شبیه‌سازی مدل'],
    ['exp', '📊 آزمایش‌های من']]

  return (
    <>
      <div className="card">
        <h3>🧪 آزمایشگاه شبیه‌سازی پژوهش — دیتاساینس درون سامانه</h3>
        <div className="demo-banner">
          <b>🎯 چرخهٔ کامل:</b> دیتاست پژوهش را بارگذاری کنید (CSV/Excel)، متغیرها را کاوش کنید
          (توزیع، همبستگی، کای‌دو، ANOVA)، سپس مدل‌های رگرسیون، طبقه‌بندی و خوشه‌بندی را شبیه‌سازی و مقایسه کنید.
          خلاصهٔ هر آزمایش را می‌توانید در بخش «یافته‌ها»ی سند پژوهش درج کنید.
        </div>
        <div className="row" style={{ gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
          {TABS.map(([k, l]) => (
            <button key={k} className={`btn ${tab === k ? '' : 'ghost'}`} onClick={() => setTab(k)}>{l}</button>
          ))}
        </div>
      </div>
      {tab === 'ds' && <DatasetsTab list={list} reload={reload} selected={selected} onSelect={(d) => { setSelected(d); setTab('explore') }} />}
      {tab === 'explore' && <ExploreTab dataset={selected} datasets={list} onSelect={setSelected} />}
      {tab === 'simulate' && <SimulateTab dataset={selected} datasets={list} onSelect={setSelected} meta={meta} reload={reload} goExp={() => setTab('exp')} />}
      {tab === 'exp' && <ExperimentsTab list={list} />}
    </>
  )
}

/* ==================== تب دیتاست‌ها ==================== */

function DatasetsTab({ list, reload, selected, onSelect }) {
  const [file, setFile] = useState(null)
  const [title, setTitle] = useState('')
  const [desc, setDesc] = useState('')
  const [busy, setBusy] = useState(false)
  const [detail, setDetail] = useState(null)

  const upload = async () => {
    if (!file) return alert('فایل CSV یا Excel را انتخاب کنید')
    setBusy(true)
    try {
      await api('/lab/datasets', { method: 'POST', form: (() => {
        const fd = new FormData()
        fd.append('file', file)
        fd.append('title', title || file.name)
        fd.append('description', desc)
        return fd
      })() })
      setFile(null); setTitle(''); setDesc('')
      document.getElementById('lab-file') && (document.getElementById('lab-file').value = '')
      reload()
    } catch (e) { alert(e.message) } finally { setBusy(false) }
  }
  const openDetail = async (id) => setDetail(await api(`/lab/datasets/${id}`).catch(e => { alert(e.message); return null }))
  const remove = async (d) => {
    if (!confirm(`دیتاست «${d.title}» و همهٔ آزمایش‌هایش حذف شود؟`)) return
    await api(`/lab/datasets/${d.id}`, { method: 'DELETE' }).catch(e => alert(e.message))
    reload()
  }

  return (
    <>
      <div className="card">
        <h4>📤 بارگذاری دیتاست پژوهش</h4>
        <div style={{ display: 'grid', gap: 8, margin: '8px 0' }}>
          <input type="file" id="lab-file" accept=".csv,.txt,.tsv,.xlsx,.xlsm"
                 onChange={e => setFile(e.target.files?.[0] || null)} />
          <div className="grid cols-2">
            <input placeholder="عنوان دیتاست (مثلاً: پرسشنامهٔ ترک تحصیل)" value={title}
                   onChange={e => setTitle(e.target.value)} />
            <input placeholder="توضیح کوتاه (اختیاری)" value={desc} onChange={e => setDesc(e.target.value)} />
          </div>
          <button className="btn" disabled={busy} onClick={upload}>{busy ? 'در حال بارگذاری…' : 'بارگذاری و تشخیص ستون‌ها'}</button>
          <div className="hint">فرمت‌های مجاز: CSV / TXT / TSV / XLSX — حداکثر ۵ مگابایت، ۱۰٬۰۰۰ ردیف و ۲۰۰ ستون.
            نوع هر ستون (عددی/مقوله‌ای) به‌صورت خودکار تشخیص داده می‌شود؛ ارقام فارسی هم پشتیبانی می‌شود.</div>
        </div>
      </div>

      <div className="grid cols-2">
        {list.map(d => (
          <div key={d.id} className="card" style={selected?.id === d.id ? { outline: '2px solid var(--primary)' } : null}>
            <h4>🗂️ {d.title}</h4>
            <div className="hint">{toFa(d.n_rows)} ردیف · {toFa(d.n_cols)} ستون · {fmtDateTime(d.created_at)}</div>
            {d.description && <div className="hint">{d.description}</div>}
            <div className="row" style={{ gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
              <button className="btn small" onClick={() => onSelect(d)}>انتخاب برای تحلیل</button>
              <button className="btn small ghost" onClick={() => openDetail(d.id)}>پیش‌نمایش</button>
              <button className="btn small ghost" onClick={() => remove(d)}>حذف</button>
            </div>
          </div>
        ))}
        {list.length === 0 && <div className="card hint">هنوز دیتاستی بارگذاری نکرده‌اید — اولین فایل را بالای صفحه اضافه کنید.</div>}
      </div>

      {detail && (
        <div className="card">
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <h4>👁️ پیش‌نمایش «{detail.title}»</h4>
            <button className="btn small ghost" onClick={() => setDetail(null)}>بستن</button>
          </div>
          <div className="hint">{toFa(detail.n_rows)} ردیف — نمایش ۲۰ ردیف اول</div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', fontSize: 12.5, borderCollapse: 'collapse', direction: 'ltr' }}>
              <thead><tr>{detail.columns_meta.map(c =>
                <th key={c.name} style={{ borderBottom: '2px solid #e4eaf2', padding: '4px 8px', textAlign: 'left' }}>
                  {c.name}<div style={{ fontSize: 10, fontWeight: 400, opacity: .6 }}>{c.dtype === 'numeric' ? 'عددی' : 'مقوله‌ای'}</div>
                </th>)}</tr></thead>
              <tbody>{detail.preview.map((r, i) => (
                <tr key={i}>{detail.columns_meta.map(c =>
                  <td key={c.name} style={{ borderBottom: '1px dashed #e4eaf2', padding: '3px 8px' }}>
                    {r[c.name] ?? '—'}</td>)}</tr>
              ))}</tbody>
            </table>
          </div>
        </div>
      )}
    </>
  )
}

/* ==================== تب کاوش و نمودار ==================== */

function DatasetPicker({ dataset, datasets, onSelect }) {
  return (
    <div className="card">
      <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
        <b>دیتاست:</b>
        <select value={dataset?.id || ''} onChange={e => onSelect(datasets.find(x => x.id === Number(e.target.value)) || null)}>
          <option value="">— انتخاب کنید —</option>
          {datasets.map(d => <option key={d.id} value={d.id}>{d.title} ({toFa(d.n_rows)}×{toFa(d.n_cols)})</option>)}
        </select>
        {!datasets.length && <span className="hint">اول از تب «دیتاست‌ها» فایل بارگذاری کنید</span>}
      </div>
    </div>
  )
}

function ExploreTab({ dataset, datasets, onSelect }) {
  const [profile, setProfile] = useState(null)
  const [corr, setCorr] = useState(null)
  const [corrMethod, setCorrMethod] = useState('pearson')
  const [sc, setSc] = useState({ x: '', y: '', hue: '', data: null })
  const [ct, setCt] = useState({ a: '', b: '', data: null })
  const [av, setAv] = useState({ target: '', group: '', data: null })

  const loadProfile = (ds) => {
    if (!ds) { setProfile(null); setCorr(null); return }
    api(`/lab/datasets/${ds.id}/profile`).then(setProfile).catch(e => alert(e.message))
  }
  useEffect(() => { loadProfile(dataset) }, [dataset?.id])
  const loadCorr = (m = corrMethod) => {
    if (!dataset) return
    api(`/lab/datasets/${dataset.id}/correlations?method=${m}`).then(c => { setCorrMethod(m); setCorr(c) }).catch(e => alert(e.message))
  }
  useEffect(() => { if (dataset) loadCorr(corrMethod) }, [dataset?.id])

  const numCols = (profile?.columns || []).filter(c => c.dtype === 'numeric')
  const catCols = (profile?.columns || []).filter(c => c.dtype !== 'numeric')

  const drawScatter = async () => {
    if (!sc.x || !sc.y) return alert('دو متغیر عددی را انتخاب کنید')
    const q = `?x=${encodeURIComponent(sc.x)}&y=${encodeURIComponent(sc.y)}` + (sc.hue ? `&hue=${encodeURIComponent(sc.hue)}` : '')
    const data = await api(`/lab/datasets/${dataset.id}/scatter${q}`).catch(e => { alert(e.message); return null })
    setSc(s => ({ ...s, data }))
  }
  const drawCt = async () => {
    if (!ct.a || !ct.b) return alert('دو ستون مقوله‌ای انتخاب کنید')
    const data = await api(`/lab/datasets/${dataset.id}/crosstab?a=${encodeURIComponent(ct.a)}&b=${encodeURIComponent(ct.b)}`).catch(e => { alert(e.message); return null })
    setCt(s => ({ ...s, data }))
  }
  const drawAv = async () => {
    if (!av.target || !av.group) return alert('متغیر عددی و ستون گروه را انتخاب کنید')
    const data = await api(`/lab/datasets/${dataset.id}/anova?target=${encodeURIComponent(av.target)}&group=${encodeURIComponent(av.group)}`).catch(e => { alert(e.message); return null })
    setAv(s => ({ ...s, data }))
  }

  if (!dataset) return <DatasetPicker dataset={dataset} datasets={datasets} onSelect={onSelect} />

  return (
    <>
      <DatasetPicker dataset={dataset} datasets={datasets} onSelect={onSelect} />

      {profile && (
        <div className="card">
          <h4>📋 نمای کلی — {profile.title}</h4>
          <div className="row" style={{ gap: 8, flexWrap: 'wrap', marginTop: 6 }}>
            <Metric label="ردیف‌ها" value={toFa(profile.n_rows)} />
            <Metric label="ستون‌ها" value={toFa(profile.n_cols)} />
            <Metric label="ردیف تکراری" value={toFa(profile.duplicate_rows)} />
            <Metric label="سلول گمشده" value={toFa(profile.missing_cells)} hint={`${toFa(profile.missing_ratio * 100)}٪ کل سلول‌ها`} />
          </div>
        </div>
      )}

      {profile && numCols.length > 0 && (
        <div className="card">
          <h4>📊 توزیع متغیرهای عددی</h4>
          <div className="hint" style={{ marginBottom: 8 }}>
            میانگین، انحراف معیار، چارک‌ها و تعداد پرت (IQR) هر متغیر — روی نمودار بکشید برای جزئیات.
          </div>
          <div className="grid cols-2">
            {numCols.slice(0, 6).map(c => (
              <div key={c.name} style={{ border: '1px solid #e4eaf2', borderRadius: 10, padding: 8 }}>
                <b style={{ fontSize: 13 }}>{c.name}</b>
                <div className="hint">میانگین {toFa(c.mean)} · انحراف {toFa(c.std)} · پرت‌ها {toFa(c.outliers)}</div>
                <Chart type="bar" height={150} data={{
                  labels: c.hist.edges.slice(0, -1).map((e, i) => toFa(((e + c.hist.edges[i + 1]) / 2).toFixed(1))),
                  datasets: [{ label: c.name, data: c.hist.counts, backgroundColor: 'rgba(37,99,235,.55)', borderRadius: 3 }],
                }} options={{ plugins: { legend: { display: false } }, scales: { x: { ticks: { font: { size: 9 } } } } }} />
              </div>
            ))}
          </div>
        </div>
      )}

      {profile && catCols.length > 0 && (
        <div className="card">
          <h4>🥧 مقوله‌های متغیرهای غیرعددی</h4>
          <div className="grid cols-2">
            {catCols.slice(0, 6).map(c => (
              <div key={c.name} style={{ border: '1px solid #e4eaf2', borderRadius: 10, padding: 8 }}>
                <b style={{ fontSize: 13 }}>{c.name}</b>
                <div className="hint">{toFa(c.n_unique)} مقدار یکتا · {toFa(c.n_missing)} گمشده</div>
                <Chart type="bar" height={150} data={{
                  labels: c.top.map(t => t.value),
                  datasets: [{ label: c.name, data: c.top.map(t => t.count),
                               backgroundColor: PALETTE.slice(0, c.top.length), borderRadius: 3 }],
                }} options={{ indexAxis: 'y', plugins: { legend: { display: false } } }} />
              </div>
            ))}
          </div>
        </div>
      )}

      {corr && (
        <div className="card">
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            <h4>🌡️ ماتریس همبستگی</h4>
            <select value={corrMethod} onChange={e => loadCorr(e.target.value)}>
              <option value="pearson">پیرسون (خطی)</option>
              <option value="spearman">اسپیرمن (رتبه‌ای)</option>
            </select>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', fontSize: 11.5, direction: 'ltr', margin: '8px 0' }}>
              <thead><tr>
                <th style={{ padding: '4px 6px' }}></th>
                {corr.columns.map(c => <th key={c} style={{ padding: '4px 6px', fontSize: 10.5 }}>{c}</th>)}
              </tr></thead>
              <tbody>{corr.matrix.map((row, i) => (
                <tr key={i}>
                  <th style={{ padding: '4px 6px', fontSize: 10.5, textAlign: 'left' }}>{corr.columns[i]}</th>
                  {row.map((v, j) => (
                    <td key={j} style={{ background: heatColor(v), color: Math.abs(v || 0) > .55 ? '#fff' : '#1f2937',
                                         padding: '5px 7px', textAlign: 'center', borderRadius: 3 }}>
                      {v === null ? '—' : toFa(v.toFixed(2))}</td>
                  ))}
                </tr>
              ))}</tbody>
            </table>
          </div>
          {corr.strong_pairs.length > 0 && (
            <div className="hint">🔗 جفت‌های قوی (|r| ≥ 0.7):
              {corr.strong_pairs.map(s => <span key={s.a + s.b} className="badge" style={{ margin: 2 }}>
                {s.a} ↔ {s.b}: {toFa(s.r)} ({s.direction})</span>)}
            </div>
          )}
          <div className="hint" style={{ marginTop: 4 }}>💡 {corr.note}</div>
        </div>
      )}

      <div className="card">
        <h4>✳️ نمودار پراکندگی دو متغیر</h4>
        <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
          <select value={sc.x} onChange={e => setSc({ ...sc, x: e.target.value })}>
            <option value="">متغیر X…</option>
            {numCols.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
          </select>
          <select value={sc.y} onChange={e => setSc({ ...sc, y: e.target.value })}>
            <option value="">متغیر Y…</option>
            {numCols.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
          </select>
          <select value={sc.hue} onChange={e => setSc({ ...sc, hue: e.target.value })}>
            <option value="">رنگ‌بندی (اختیاری)…</option>
            {catCols.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
          </select>
          <button className="btn small" onClick={drawScatter}>رسم</button>
        </div>
        {sc.data && <>
          <div className="hint" style={{ marginTop: 6 }}>{toFa(sc.data.n_valid)} نقطهٔ معتبر ·
            ضریب همبستگی r = {toFa(sc.data.trend.r ?? '—')} ·
            شیب خط روند = {toFa(sc.data.trend.slope ?? '—')}</div>
          <Chart type="scatter" height={300} data={{
            datasets: [
              ...sc.data.groups.slice(0, 8).map((g, i) => ({
                label: g.value || 'همه',
                data: sc.data.points.filter(p => (p.g || '') === (g.value || '')).map(p => ({ x: p.x, y: p.y })),
                backgroundColor: PALETTE[i % PALETTE.length] + '99', pointRadius: 3.5,
              })),
              ...(sc.data.trend.slope !== null ? [{
                label: 'خط روند', type: 'line',
                data: (() => { const xs = sc.data.points.map(p => p.x); const mn = Math.min(...xs), mx = Math.max(...xs)
                  return [{ x: mn, y: sc.data.trend.slope * mn + sc.data.trend.intercept },
                          { x: mx, y: sc.data.trend.slope * mx + sc.data.trend.intercept }] })(),
                borderColor: '#111827', borderDash: [6, 4], pointRadius: 0, borderWidth: 1.5,
              }] : []),
            ],
          }} options={{ scales: { x: { type: 'linear' }, y: { type: 'linear' } } }} />
        </>}
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h4>🔀 جدول توافقی + کای‌دو</h4>
          <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
            <select value={ct.a} onChange={e => setCt({ ...ct, a: e.target.value })}>
              <option value="">ستون A…</option>
              {catCols.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
            </select>
            <select value={ct.b} onChange={e => setCt({ ...ct, b: e.target.value })}>
              <option value="">ستون B…</option>
              {catCols.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
            </select>
            <button className="btn small" onClick={drawCt}>تحلیل</button>
          </div>
          {ct.data && <>
            <div style={{ overflowX: 'auto', marginTop: 8 }}>
              <table style={{ borderCollapse: 'collapse', fontSize: 12 }}>
                <thead><tr><th></th>{ct.data.cols_labels.map(l => <th key={l} style={{ padding: '4px 8px' }}>{l}</th>)}</tr></thead>
                <tbody>{ct.data.rows_labels.map((rl, i) => (
                  <tr key={rl}><th style={{ padding: '4px 8px' }}>{rl}</th>
                    {ct.data.table[i].map((v, j) => <td key={j} style={{ padding: '4px 10px', textAlign: 'center',
                      background: v ? 'rgba(37,99,235,.12)' : 'transparent' }}>{toFa(v)}</td>)}</tr>
                ))}</tbody>
              </table>
            </div>
            <div className="hint" style={{ marginTop: 6 }}>کای‌دو = {toFa(ct.data.chi2)} · درجه آزادی = {toFa(ct.data.dof)} ·
              p = {toFa(ct.data.p_value)} — {ct.data.note}</div>
          </>}
        </div>

        <div className="card">
          <h4>📐 تحلیل واریانس یک‌راهه (ANOVA)</h4>
          <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
            <select value={av.target} onChange={e => setAv({ ...av, target: e.target.value })}>
              <option value="">متغیر عددی…</option>
              {numCols.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
            </select>
            <select value={av.group} onChange={e => setAv({ ...av, group: e.target.value })}>
              <option value="">ستون گروه…</option>
              {catCols.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
            </select>
            <button className="btn small" onClick={drawAv}>محاسبه</button>
          </div>
          {av.data && <>
            <div className="row" style={{ gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
              <Metric label="F" value={toFa(av.data.F)} />
              <Metric label="p-value" value={toFa(av.data.p_value)} />
              <Metric label="اندازهٔ اثر η²" value={toFa(av.data.eta_squared ?? '—')} />
            </div>
            <table style={{ borderCollapse: 'collapse', fontSize: 12, marginTop: 8, width: '100%' }}>
              <thead><tr><th style={{ padding: 4 }}>گروه</th><th>تعداد</th><th>میانگین</th><th>انحراف معیار</th></tr></thead>
              <tbody>{av.data.groups.map(g => (
                <tr key={g.value}><td style={{ padding: '4px 6px' }}>{g.value}</td><td style={{ textAlign: 'center' }}>{toFa(g.n)}</td>
                  <td style={{ textAlign: 'center' }}>{toFa(g.mean)}</td><td style={{ textAlign: 'center' }}>{toFa(g.std)}</td></tr>
              ))}</tbody>
            </table>
            <div className="hint" style={{ marginTop: 4 }}>💡 {av.data.note}</div>
          </>}
        </div>
      </div>
    </>
  )
}

/* ==================== تب شبیه‌سازی مدل ==================== */

function SimulateTab({ dataset, datasets, onSelect, meta, reload, goExp }) {
  const [task, setTask] = useState('regression')
  const [model, setModel] = useState('linear')
  const [target, setTarget] = useState('')
  const [features, setFeatures] = useState([])
  const [params, setParams] = useState({ test_size: 0.25, random_state: 42, scaled: false, k: '' })
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)

  const taskDef = meta?.tasks.find(t => t.key === task)
  useEffect(() => { setModel(taskDef?.models[0]?.key || '') }, [task])
  useEffect(() => { setTarget(''); setFeatures([]); setResult(null) }, [dataset?.id])
  useEffect(() => {
    setParams(p => ({ ...p, scaled: task === 'clustering' })); setResult(null)
  }, [task])

  const cols = dataset?.columns_meta || []
  const numCols = cols.filter(c => c.dtype === 'numeric').map(c => c.name)
  const catCols = cols.filter(c => c.dtype !== 'numeric').map(c => c.name)
  const eligibleTargets = task === 'regression' ? numCols : (task === 'classification' ? cols.map(c => c.name) : [])

  const toggleFeature = (name) => setFeatures(f => f.includes(name) ? f.filter(x => x !== name) : [...f, name])

  const run = async () => {
    if (!dataset) return alert('دیتاست را انتخاب کنید')
    setBusy(true); setResult(null)
    try {
      const e = await api('/lab/experiments', { method: 'POST', body: {
        dataset_id: dataset.id, task, model, target: task === 'clustering' ? '' : target,
        features, title: '', params,
      } })
      setResult(e)
      reload()
    } catch (e) { alert(e.message) } finally { setBusy(false) }
  }

  return (
    <>
      <DatasetPicker dataset={dataset} datasets={datasets} onSelect={onSelect} />
      <div className="card">
        <h4>⚙️ پیکربندی آزمایش</h4>
        <div className="grid cols-2" style={{ marginTop: 8 }}>
          <div>
            <div className="hint">وظیفه</div>
            <select value={task} onChange={e => setTask(e.target.value)}>
              {(meta?.tasks || []).map(t => <option key={t.key} value={t.key}>{t.title}</option>)}
            </select>
          </div>
          <div>
            <div className="hint">مدل</div>
            <select value={model} onChange={e => setModel(e.target.value)}>
              {(taskDef?.models || []).map(m => <option key={m.key} value={m.key}>{m.title}</option>)}
            </select>
          </div>
          {task !== 'clustering' && (
            <div>
              <div className="hint">متغیر هدف (وابسته)</div>
              <select value={target} onChange={e => setTarget(e.target.value)}>
                <option value="">— انتخاب کنید —</option>
                {eligibleTargets.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          )}
          <div>
            <div className="hint">نسبت دادهٔ آزمون</div>
            <input type="number" min="0.1" max="0.5" step="0.05" value={params.test_size}
                   onChange={e => setParams({ ...params, test_size: Number(e.target.value) })} />
          </div>
          <div>
            <div className="hint">بذر تصادفی (تکرارپذیری)</div>
            <input type="number" value={params.random_state}
                   onChange={e => setParams({ ...params, random_state: Number(e.target.value) })} />
          </div>
          {task === 'clustering' && (
            <div>
              <div className="hint">تعداد خوشه K (خالی = انتخاب خودکار)</div>
              <input type="number" min="2" max="8" value={params.k}
                     onChange={e => setParams({ ...params, k: e.target.value ? Number(e.target.value) : '' })} />
            </div>
          )}
          {(model === 'ridge' || model === 'lasso') && (
            <div>
              <div className="hint">ضریب انضباط α</div>
              <input type="number" step="0.05" min="0" value={params.alpha ?? ''}
                     onChange={e => setParams({ ...params, alpha: e.target.value ? Number(e.target.value) : '' })} />
            </div>
          )}
          {model.startsWith('tree') || model === 'forest' ? (
            <div>
              <div className="hint">{model === 'forest' ? 'تعداد درخت‌ها' : 'بیشینهٔ عمق درخت (خالی = نامحدود)'}</div>
              <input type="number" min="1" value={params[model === 'forest' ? 'n_estimators' : 'max_depth'] ?? ''}
                     onChange={e => setParams({ ...params, [model === 'forest' ? 'n_estimators' : 'max_depth']: e.target.value ? Number(e.target.value) : '' })} />
            </div>
          ) : null}
          {(model === 'knn') && (
            <div>
              <div className="hint">تعداد همسایه‌ها K</div>
              <input type="number" min="1" value={params.knn_k ?? ''}
                     onChange={e => setParams({ ...params, knn_k: e.target.value ? Number(e.target.value) : '' })} />
            </div>
          )}
          <div style={{ display: 'flex', alignItems: 'end', gap: 6 }}>
            <label style={{ display: 'flex', gap: 6, alignItems: 'center', cursor: 'pointer' }}>
              <input type="checkbox" checked={params.scaled} disabled={task === 'clustering'}
                     onChange={e => setParams({ ...params, scaled: e.target.checked })} />
              استانداردسازی ویژگی‌ها (StandardScaler)
            </label>
          </div>
        </div>

        {task !== 'clustering' && (
          <div style={{ marginTop: 10 }}>
            <div className="hint">متغیرهای مستقل (ویژگی‌ها) — حداقل یکی را انتخاب کنید:</div>
            <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
              {[...numCols, ...catCols].map(c => (
                <label key={c} className="badge" style={{ cursor: 'pointer', padding: '4px 10px',
                  background: features.includes(c) ? 'var(--primary)' : 'transparent',
                  color: features.includes(c) ? '#fff' : 'var(--muted)' }}>
                  <input type="checkbox" checked={features.includes(c)} onChange={() => toggleFeature(c)}
                         style={{ display: 'none' }} />
                  {c} <span style={{ opacity: .7, fontSize: 10 }}>{numCols.includes(c) ? '🔢' : '🔤'}</span>
                </label>
              ))}
            </div>
          </div>
        )}
        {task === 'clustering' && (
          <div className="hint" style={{ marginTop: 8 }}>برای خوشه‌بندی حداقل دو متغیر عددی لازم است — رنگ‌بندی در نمودار از خوشه‌ها می‌آید.</div>
        )}
        <div className="row" style={{ gap: 8, marginTop: 12 }}>
          <button className="btn" onClick={run} disabled={busy || !dataset}>
            {busy ? '⏳ در حال اجرا…' : '🚀 اجرای شبیه‌سازی'}
          </button>
          <button className="btn ghost" onClick={goExp}>مشاهدهٔ آزمایش‌های ثبت‌شده</button>
        </div>
      </div>

      {result && <ExperimentResult exp={result} />}
    </>
  )
}

/* ==================== نمایش نتایج آزمایش (مشترک) ==================== */

function ExperimentResult({ exp }) {
  const [predict, setPredict] = useState(null)
  const [rowInput, setRowInput] = useState({})
  const [docs, setDocs] = useState([])
  const [docSections, setDocSections] = useState([])
  const [attachTo, setAttachTo] = useState({ doc_id: '', section_id: '' })
  const m = exp.metrics || {}
  const a = exp.artifacts || {}

  useEffect(() => { api('/research/docs/mine').then(setDocs).catch(() => {}) }, [])
  useEffect(() => {
    if (!attachTo.doc_id) { setDocSections([]); return }
    api(`/research/docs/${attachTo.doc_id}`).then(d => setDocSections(d.sections || [])).catch(() => {})
  }, [attachTo.doc_id])

  const runPredict = async () => {
    try {
      const p = await api(`/lab/experiments/${exp.id}/predict`, { method: 'POST', body: { row: rowInput } })
      setPredict(p)
    } catch (e) { alert(e.message) }
  }
  const attach = async () => {
    if (!attachTo.doc_id) return alert('سند مقصد را انتخاب کنید')
    try {
      const r = await api(`/lab/experiments/${exp.id}/attach-doc`, { method: 'POST', body: {
        doc_id: Number(attachTo.doc_id), section_id: attachTo.section_id ? Number(attachTo.section_id) : null } })
      alert(`خلاصهٔ نتایج در بخش «${r.section_heading}» درج شد — آن را بازنویسی و تفسیر کنید.`)
    } catch (e) { alert(e.message) }
  }

  const metricRow = exp.task === 'regression' ? (
    <>
      <Metric label="R² آموزش" value={toFa(m.r2_train)} />
      <Metric label="R² آزمون" value={toFa(m.r2_test)} hint="مهم‌ترین سنجهٔ برازش" />
      <Metric label="MAE آزمون" value={toFa(m.mae_test)} />
      <Metric label="RMSE آزمون" value={toFa(m.rmse_test)} />
      <Metric label="MAPE ٪" value={toFa(m.mape_test)} />
      <Metric label="داده" value={`${toFa(m.n_train)}/${toFa(m.n_test)}`} hint="آموزش/آزمون" />
    </>
  ) : exp.task === 'classification' ? (
    <>
      <Metric label="دقت آموزش" value={toFa(m.accuracy_train)} />
      <Metric label="دقت آزمون" value={toFa(m.accuracy_test)} />
      <Metric label="دقت متوازن" value={toFa(m.balanced_accuracy_test)} hint="مناسب رده‌های نامتوازن" />
      <Metric label="F1 کلان" value={toFa(m.f1_macro_test)} />
      {m.roc_auc_test !== undefined && <Metric label="AUC" value={toFa(m.roc_auc_test)} />}
      <Metric label="داده" value={`${toFa(m.n_train)}/${toFa(m.n_test)}`} hint="آموزش/آزمون" />
    </>
  ) : (
    <>
      <Metric label="تعداد خوشه" value={toFa(m.n_clusters)} hint={m.auto ? 'انتخاب خودکار K' : 'K دستی'} />
      <Metric label="ضریب سایه‌لو" value={toFa(m.silhouette)} hint="نزدیک ۱ = تفکیک بهتر" />
      {m.inertia !== undefined && <Metric label="اینرسی" value={toFa(m.inertia)} />}
      {m.noise_points !== undefined && <Metric label="نقاط نویز" value={toFa(m.noise_points)} />}
      <Metric label="ردیف‌ها" value={toFa(m.n_rows_total)} />
    </>
  )

  const scatterColors = ['#2563eb', '#e11d48', '#059669', '#d97706', '#7c3aed', '#0891b2', '#65a30d', '#be123c']

  return (
    <div className="card" style={{ borderRight: '4px solid var(--primary)' }}>
      <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap' }}>
        <h4>📈 نتایج آزمایش #{toFa(exp.id)} — {exp.title || exp.model_fa}</h4>
        <span className="badge">{exp.task_fa}</span>
      </div>
      <div className="hint" style={{ marginTop: 4 }}>
        مدل: <b>{exp.model_fa}</b> · هدف: {exp.target || '—'} · ویژگی‌ها: {toFa(exp.features.length)} ·
        بذر: {toFa(exp.params.random_state)} · {fmtDateTime(exp.created_at)}
      </div>
      <div className="row" style={{ gap: 8, flexWrap: 'wrap', margin: '10px 0' }}>{metricRow}</div>

      {exp.task === 'regression' && (
        <>
          <div className="grid cols-2">
            <div>
              <b style={{ fontSize: 13 }}>واقعی در برابر پیش‌بینی (دادهٔ آزمون)</b>
              <Chart type="scatter" height={260} data={{
                datasets: [
                  { label: 'نمونه‌های آزمون', data: (a.pred_actual || []).map(p => ({ x: p.actual, y: p.predicted })),
                    backgroundColor: 'rgba(37,99,235,.6)', pointRadius: 3.5 },
                  { label: 'خط=y', type: 'line',
                    data: (() => { const xs = (a.pred_actual || []).map(p => p.actual).filter(v => v !== null)
                      const mn = Math.min(...xs), mx = Math.max(...xs); return [{ x: mn, y: mn }, { x: mx, y: mx }] })(),
                    borderColor: '#e11d48', borderDash: [6, 4], pointRadius: 0 },
                ],
              }} options={{ scales: { x: { type: 'linear', title: { display: true, text: 'واقعی' } },
                y: { type: 'linear', title: { display: true, text: 'پیش‌بینی' } } } }} />
            </div>
            <div>
              <b style={{ fontSize: 13 }}>توزیع پسماندها (واقعی − پیش‌بینی)</b>
              <Chart type="bar" height={260} data={{
                labels: a.residual_hist?.edges.slice(0, -1).map((e, i) => toFa(((e + a.residual_hist.edges[i + 1]) / 2).toFixed(2))),
                datasets: [{ data: a.residual_hist?.counts || [], backgroundColor: 'rgba(5,150,105,.6)', borderRadius: 3 }],
              }} options={{ plugins: { legend: { display: false } } }} />
            </div>
          </div>
        </>
      )}

      {exp.task === 'classification' && (
        <div className="grid cols-2">
          <div>
            <b style={{ fontSize: 13 }}>ماتریس درهم‌ریختگی</b>
            <ConfusionGrid conf={a.confusion} />
            <table style={{ borderCollapse: 'collapse', fontSize: 12, marginTop: 10, width: '100%' }}>
              <thead><tr><th style={{ padding: 4 }}>رده</th><th>دقت</th><th>بازیابی</th><th>F1</th><th>پشتوانه</th></tr></thead>
              <tbody>{(a.per_class || []).map(pc => (
                <tr key={pc.label}><td style={{ padding: '4px 6px' }}>{pc.label}</td>
                  <td style={{ textAlign: 'center' }}>{toFa(pc.precision)}</td><td style={{ textAlign: 'center' }}>{toFa(pc.recall)}</td>
                  <td style={{ textAlign: 'center' }}>{toFa(pc.f1)}</td><td style={{ textAlign: 'center' }}>{toFa(pc.support)}</td></tr>
              ))}</tbody>
            </table>
          </div>
          <div>
            {a.roc && <>
              <b style={{ fontSize: 13 }}>منحنی ROC — AUC = {toFa(a.roc.auc)}</b>
              <Chart type="line" height={240} data={{
                datasets: [
                  { label: `کلاس مثبت: ${a.roc.positive_class}`, data: a.roc.points.map(p => ({ x: p.fpr, y: p.tpr })),
                    borderColor: '#2563eb', borderWidth: 2, pointRadius: 0 },
                  { label: 'تصادفی', data: [{ x: 0, y: 0 }, { x: 1, y: 1 }], borderColor: '#9ca3af',
                    borderDash: [4, 4], pointRadius: 0 },
                ],
              }} options={{ scales: { x: { type: 'linear', title: { display: true, text: 'FPR' }, min: 0, max: 1 },
                y: { type: 'linear', title: { display: true, text: 'TPR' }, min: 0, max: 1 } } }} />
            </>}
          </div>
        </div>
      )}

      {exp.task === 'clustering' && (
        <>
          <div className="grid cols-2">
            <div>
              <b style={{ fontSize: 13 }}>خوشه‌ها در فضای دوبعدی (PCA{a.pca_variance ? ` — واریانس تبیین‌شده: ${toFa((a.pca_variance[0] + (a.pca_variance[1] || 0)) * 100)}٪` : ''})</b>
              <Chart type="scatter" height={280} data={{
                datasets: Object.keys(m.cluster_sizes || {}).map((k, i) => ({
                  label: `خوشهٔ ${toFa(k)}`,
                  data: (a.pca_scatter || []).filter(p => String(p.cluster) === k).map(p => ({ x: p.x, y: p.y })),
                  backgroundColor: scatterColors[i % scatterColors.length] + '99', pointRadius: 3.5,
                })).concat((a.pca_centroids || []).map((c, i) => ({
                  label: `مرکز ${toFa(c.cluster)}`, data: [{ x: c.x, y: c.y }],
                  backgroundColor: '#111827', pointStyle: 'crossRot', radius: 8,
                }))),
              }} options={{ scales: { x: { type: 'linear' }, y: { type: 'linear' } } }} />
            </div>
            <div>
              {m.elbow && <>
                <b style={{ fontSize: 13 }}>روش آرنج (اینرسی بر حسب K)</b>
                <Chart type="line" height={280} data={{
                  labels: m.elbow.map(e => toFa(e.k)),
                  datasets: [{ label: 'اینرسی', data: m.elbow.map(e => e.inertia),
                               borderColor: '#d97706', backgroundColor: 'rgba(217,119,6,.15)', fill: true, tension: .25 }],
                }} options={{ plugins: { legend: { display: false } } }} />
              </>}
            </div>
          </div>
          <b style={{ fontSize: 13 }}>پروفایل خوشه‌ها (میانگین ویژگی‌ها در مقیاس اصلی):</b>
          <table style={{ borderCollapse: 'collapse', fontSize: 12, marginTop: 6, width: '100%' }}>
            <thead><tr><th style={{ padding: 4 }}>خوشه</th><th>تعداد</th>
              {(a.cluster_profile?.[0]?.means ? Object.keys(a.cluster_profile[0].means) : []).map(k => <th key={k}>{k}</th>)}</tr></thead>
            <tbody>{(a.cluster_profile || []).map(p => (
              <tr key={p.cluster}><td style={{ padding: '4px 6px' }}>خوشهٔ {toFa(p.cluster)}</td>
                <td style={{ textAlign: 'center' }}>{toFa(p.size)}</td>
                {Object.values(p.means).map((v, i) => <td key={i} style={{ textAlign: 'center' }}>{toFa(v)}</td>)}</tr>
            ))}</tbody>
          </table>
        </>
      )}

      {(a.coefficients || []).length > 0 && exp.task !== 'clustering' && (
        <div style={{ marginTop: 10 }}>
          <b style={{ fontSize: 13 }}>{exp.task === 'regression' ? 'ضرایب / اهمیت متغیرها (۲۰ مورد نخست)' : 'اهمیت متغیرها (۲۰ مورد نخست)'}</b>
          <div className="row" style={{ gap: 4, flexWrap: 'wrap', marginTop: 6 }}>
            {a.coefficients.map(c => (
              <span key={c.feature} className="badge">{c.feature}: {toFa(c.value)}</span>
            ))}
          </div>
        </div>
      )}

      {/* ---------- پیش‌بینی ردیف جدید ---------- */}
      {exp.task !== 'clustering' && (
        <div style={{ marginTop: 14, borderTop: '1px dashed #e4eaf2', paddingTop: 10 }}>
          <b style={{ fontSize: 13 }}>🔮 پیش‌بینی برای یک نمونهٔ جدید</b>
          <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
            {exp.features.map(f => (
              <input key={f} placeholder={f} style={{ width: 150 }} value={rowInput[f] ?? ''}
                     onChange={e => setRowInput({ ...rowInput, [f]: e.target.value === '' ? null : e.target.value })} />
            ))}
            <button className="btn small" onClick={runPredict}>پیش‌بینی</button>
          </div>
          <div className="hint">برای متغیر عددی مقدار بنویسید؛ خالی بگذارید تا با میانگین آموزش جای‌گذاری شود.
            مقوله‌ها را دقیقاً همان‌طور که در دیتاست هستند وارد کنید.</div>
          {predict && (
            <div style={{ background: 'var(--primary-light)', borderRadius: 10, padding: 10, marginTop: 6 }}>
              <b>نتیجه: {exp.task === 'regression' ? toFa(predict.prediction) : predict.prediction}</b>
              {predict.probabilities && (
                <div className="hint" style={{ marginTop: 4 }}>
                  {Object.entries(predict.probabilities).map(([k, v]) => `${k}: ${toFa(v)}`).join(' · ')}
                </div>
              )}
              {predict.note && <div className="hint">{predict.note}</div>}
            </div>
          )}
        </div>
      )}

      {/* ---------- درج نتایج در سند پژوهش ---------- */}
      <div style={{ marginTop: 14, borderTop: '1px dashed #e4eaf2', paddingTop: 10 }}>
        <b style={{ fontSize: 13 }}>📝 درج خلاصهٔ نتایج در سند پژوهش تیمی</b>
        <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
          <select value={attachTo.doc_id} onChange={e => setAttachTo({ ...attachTo, doc_id: e.target.value, section_id: '' })}>
            <option value="">سند مقصد…</option>
            {docs.map(d => <option key={d.id} value={d.id}>{d.title}</option>)}
          </select>
          <select value={attachTo.section_id} onChange={e => setAttachTo({ ...attachTo, section_id: e.target.value })}>
            <option value="">بخش: خودکار (یافته‌ها/نتایج)</option>
            {docSections.map(s => <option key={s.id} value={s.id}>{toFa(s.ord)}. {s.heading}</option>)}
          </select>
          <button className="btn small" onClick={attach}>درج در سند</button>
        </div>
        <div className="hint">متن تولیدی شامل مدل، داده، سنجه‌ها و متغیرهای مهم است و به انتهای بخش اضافه می‌شود —
          بعد از درج، آن را بازنویسی و تفسیر کنید.</div>
      </div>
    </div>
  )
}

function ConfusionGrid({ conf }) {
  if (!conf) return null
  const max = Math.max(1, ...conf.matrix.flat())
  return (
    <table style={{ borderCollapse: 'collapse', marginTop: 8, fontSize: 12 }}>
      <thead><tr>
        <th style={{ padding: '4px 8px' }}>واقعی ↓ / پیش‌بینی →</th>
        {conf.labels.map(l => <th key={l} style={{ padding: '4px 10px' }}>{l}</th>)}
      </tr></thead>
      <tbody>{conf.matrix.map((row, i) => (
        <tr key={i}>
          <th style={{ padding: '4px 8px' }}>{conf.labels[i]}</th>
          {row.map((v, j) => (
            <td key={j} style={{ padding: '8px 14px', textAlign: 'center', borderRadius: 6,
              background: i === j ? `rgba(5,150,105,${0.15 + 0.65 * v / max})` : `rgba(225,29,72,${0.08 + 0.6 * v / max})`,
              fontWeight: i === j ? 700 : 400 }}>
              {toFa(v)}
            </td>
          ))}
        </tr>
      ))}</tbody>
    </table>
  )
}

/* ==================== تب آزمایش‌های من ==================== */

function ExperimentsTab({ list }) {
  const [exps, setExps] = useState([])
  const [open, setOpen] = useState(null)
  const dsMap = Object.fromEntries((list || []).map(d => [d.id, d.title]))

  const reload = () => api('/lab/experiments').then(setExps).catch(() => {})
  useEffect(() => { reload() }, [])
  const remove = async (e) => {
    if (!confirm(`آزمایش «${e.title}» حذف شود؟`)) return
    await api(`/lab/experiments/${e.id}`, { method: 'DELETE' }).catch(err => alert(err.message))
    reload()
  }

  const summary = (e) => {
    const m = e.metrics || {}
    if (e.task === 'regression') return `R² آزمون: ${toFa(m.r2_test)} · RMSE: ${toFa(m.rmse_test)}`
    if (e.task === 'classification') return `دقت: ${toFa(m.accuracy_test)} · F1 کلان: ${toFa(m.f1_macro_test)}`
    return `${toFa(m.n_clusters)} خوشه · سایه‌لو: ${toFa(m.silhouette)}`
  }

  return (
    <>
      <div className="card">
        <h4>📊 آزمایش‌های ثبت‌شده ({toFa(exps.length)})</h4>
        <div className="hint">هر آزمایش با پارامترها و نتایجش نگه داشته می‌شود تا مدل‌ها را مقایسه و در مقاله گزارش کنید.</div>
      </div>
      {exps.map(e => (
        <div key={e.id} className="card" style={{ opacity: e.status === 'failed' ? 0.65 : 1 }}>
          <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap' }}>
            <div>
              <b>#{toFa(e.id)} {e.title}</b>
              <div className="hint">{e.task_fa} · مدل: {e.model_fa} · دیتاست: {dsMap[e.dataset_id] || e.dataset_id} ·
                هدف: {e.target || '—'} · {fmtDateTime(e.created_at)}</div>
              <div className="hint">{e.status === 'failed' ? `⛔ ناموفق: ${e.error}` : '✓ ' + summary(e)}</div>
            </div>
            <div className="row" style={{ gap: 6 }}>
              {e.status === 'completed' && <button className="btn small" onClick={async () => setOpen(await api(`/lab/experiments/${e.id}`).catch(err => { alert(err.message); return null }))}>نمایش کامل</button>}
              <button className="btn small ghost" onClick={() => remove(e)}>حذف</button>
            </div>
          </div>
        </div>
      ))}
      {exps.length === 0 && <div className="card hint">هنوز آزمایشی اجرا نکرده‌اید — از تب «شبیه‌سازی مدل» شروع کنید.</div>}
      {open && (
        <div className="card">
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <h4>جزئیات آزمایش #{toFa(open.id)}</h4>
            <button className="btn small ghost" onClick={() => setOpen(null)}>بستن</button>
          </div>
          <ExperimentResult exp={open} />
        </div>
      )}
    </>
  )
}
