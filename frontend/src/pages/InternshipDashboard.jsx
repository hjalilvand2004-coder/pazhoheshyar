import React, { useEffect, useRef, useState } from 'react'
import { Chart as ChartJS, registerables } from 'chart.js'
import { api, toFa, fmtDateTime } from '../api.js'
import { INTERVAL_FA } from './practicumShared.jsx'

ChartJS.register(...registerables)

/* گزارش کارآموزی‌ها برای مدیرآموزش/مدیرگروه — لیست تمام‌شده و در جریان + نمودارهای روند */
function Chart({ type, data, options = {}, height = 260 }) {
  const ref = useRef(null)
  const [themeTick, setThemeTick] = useState(0)
  useEffect(() => {
    const onTheme = () => setThemeTick(t => t + 1)
    window.addEventListener('py:theme', onTheme)
    return () => window.removeEventListener('py:theme', onTheme)
  }, [])
  useEffect(() => {
    if (!ref.current || !data) return
    const dark = !document.documentElement.classList.contains('light-theme')
    ChartJS.defaults.color = dark ? '#cbd5e1' : '#334155'
    ChartJS.defaults.borderColor = dark ? 'rgba(255,255,255,.10)' : 'rgba(15,23,42,.12)'
    const c = new ChartJS(ref.current, {
      type, data,
      options: { responsive: true, maintainAspectRatio: false, ...options },
    })
    return () => c.destroy()
  }, [type, JSON.stringify(data), JSON.stringify(options), themeTick])
  return <div style={{ height, position: 'relative' }}>{data && <canvas ref={ref} />}</div>
}

function Metric({ label, value, hint, tone }) {
  return (
    <div style={{ background: tone ? 'var(--warn-bg, rgba(217,119,6,.12))' : 'var(--primary-light)',
                  borderRadius: 10, padding: '8px 12px', minWidth: 110 }}>
      <div className="hint" style={{ fontSize: 11 }}>{label}</div>
      <b style={{ fontSize: 17 }}>{value ?? '—'}</b>
      {hint && <div className="hint" style={{ fontSize: 10.5 }}>{hint}</div>}
    </div>
  )
}

const faWeek = (iso) => {
  try { return new Date(iso).toLocaleDateString('fa-IR', { month: 'short', day: 'numeric' }) } catch { return iso }
}

export default function InternshipDashboard() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => { api('/practicum/internship-dashboard').then(setD).catch(e => setErr(e.message)) }, [])

  if (err) return <div className="card error-box">{err}</div>
  if (!d) return <div className="card hint">در حال بارگذاری…</div>

  const s = d.stats || {}
  const series = d.series || {}

  return (
    <>
      <div className="card">
        <h3>📊 گزارش کارآموزی‌ها — مدیرآموزش / مدیرگروه</h3>
        <div className="hint">
          وضعیت همهٔ کارآموزی‌های سامانه: کارآموزی‌های تأییدنهایی‌شده با نمرهٔ از ۲۰ (سرجمع امتیاز طیف لیکرت) و
          کارآموزی‌های در جریان به‌همراه مرحلهٔ پیشرفت نسبت به زمان‌بندی استاد مربوطه.
        </div>
        <div className="row" style={{ gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
          <Metric label="کل کارآموزی‌ها" value={toFa(s.total ?? 0)} />
          <Metric label="تأییدشده" value={toFa(s.completed ?? 0)} hint="نمرهٔ نهایی ثبت شده" />
          <Metric label="در جریان" value={toFa(s.ongoing ?? 0)} hint="فعال + در انتظار پذیرش" />
          <Metric label="در انتظار پذیرش" value={toFa(s.pending_acceptance ?? 0)} hint="هنوز زمان‌بندی ندارند" />
          <Metric label="عقب از برنامه" value={toFa(s.behind_schedule ?? 0)} tone={1} hint="گزارش کمتر از زمان‌بندی" />
        </div>
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h4>📈 روند ارسال گزارش‌های پیشرفت — ۱۰ هفتهٔ اخیر</h4>
          <Chart type="line" height={230} data={{
            labels: (series.submissions_per_week || []).map(w => faWeek(w.week)),
            datasets: [{
              label: 'تعداد گزارش ثبت‌شده در هفته',
              data: (series.submissions_per_week || []).map(w => w.count),
              borderColor: '#2563eb', backgroundColor: 'rgba(37,99,235,.15)',
              fill: true, tension: 0.35, pointRadius: 3,
            }],
          }} options={{ plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } }} />
        </div>
        <div className="card">
          <h4>🧭 توزیع وضعیت کارآموزی‌ها</h4>
          <Chart type="doughnut" height={230} data={{
            labels: (series.status_distribution || []).map(x => x.fa),
            datasets: [{
              data: (series.status_distribution || []).map(x => x.count),
              backgroundColor: ['#d97706', '#2563eb', '#059669', '#64748b'],
            }],
          }} options={{ plugins: { legend: { position: 'bottom' } }, cutout: '55%' }} />
        </div>
        <div className="card" style={{ gridColumn: '1 / -1' }}>
          <h4>🎯 میانگین امتیاز طیف لیکرت به تفکیک شمارهٔ گزارش — روند کیفیت</h4>
          <Chart type="bar" height={230} data={{
            labels: (series.avg_likert_by_round || []).map(x => `گزارش ${toFa(x.round_no)}`),
            datasets: [{
              label: 'میانگین امتیاز (۰ تا ۴)',
              data: (series.avg_likert_by_round || []).map(x => x.avg),
              backgroundColor: '#059669', borderRadius: 4,
            }],
          }} options={{ plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, max: 4 } } }} />
        </div>
      </div>

      <div className="card">
        <h4>✅ کارآموزی‌های تمام‌شده ({toFa((d.completed || []).length)})</h4>
        <table className="tbl">
          <thead><tr>
            <th>دانشجو</th><th>استاد مربوطه</th><th>عنوان کارآموزی</th><th>شروع (پذیرش)</th>
            <th>تأیید نهایی</th><th>گزارش‌ها</th><th>نمرهٔ از ۲۰</th>
          </tr></thead>
          <tbody>
            {(d.completed || []).map(r => (
              <tr key={r.id}>
                <td>{r.student_name}</td><td>{r.supervisor_name}</td><td>{r.title}</td>
                <td>{fmtDateTime(r.accepted_at)}</td><td>{fmtDateTime(r.approved_at)}</td>
                <td>{toFa(r.round_count)} ({INTERVAL_FA[r.report_interval] || 'هفتگی'})</td>
                <td><b>{toFa(r.final_score ?? 0)}</b></td>
              </tr>
            ))}
            {(d.completed || []).length === 0 && <tr><td colSpan={7} className="empty">هنوز کارآموزی تأیید نهایی‌شده‌ای ثبت نشده است.</td></tr>}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h4>⏳ کارآموزی‌های در جریان و مرحلهٔ پیشرفت آن‌ها ({toFa((d.ongoing || []).length)})</h4>
        <div className="rounds">
          {(d.ongoing || []).map(r => {
            const pct = Math.min(100, Math.round(((r.progress_ratio || 0) * 100)))
            return (
              <div key={r.id} className="round-item">
                <div className="round-head">
                  <b>{r.title}</b>
                  <span className={`badge ${r.status === 'pending_acceptance' ? 'amber' : 'teal'}`}>{r.status_fa}</span>
                  {r.status === 'active' && r.behind_schedule && <span className="badge red">عقب از برنامه</span>}
                </div>
                <div className="hint">
                  {r.student_name} · استاد: {r.supervisor_name} · زمان‌بندی: {INTERVAL_FA[r.report_interval] || 'هفتگی'}
                  {r.accepted_at ? ` · از ${fmtDateTime(r.accepted_at)}` : ''}
                </div>
                {r.status === 'active' && (
                  <>
                    <div style={{ background: 'var(--border)', borderRadius: 999, height: 10, margin: '6px 0' }}>
                      <div style={{ width: `${pct}%`, background: r.behind_schedule ? '#e11d48' : '#059669',
                                    borderRadius: 999, height: 10, transition: 'width .3s' }} />
                    </div>
                    <div className="hint">
                      پیشرفت گزارش: <b>{toFa(r.round_count)}</b> گزارش ثبت‌شده از حدود {toFa(r.expected_reports || 0)} طبق زمان‌بندی
                      (حداقل {toFa(r.min_reports || 5)}) · امتیاز تجمعی: {toFa(r.current_score ?? 0)} از ۲۰
                      {(r.unscored_count || 0) > 0 && <> · {toFa(r.unscored_count)} گزارش بی‌امتیاز</>}
                      {r.last_report_at ? <> · آخرین گزارش: {fmtDateTime(r.last_report_at)}</> : ' · هنوز گزارشی ثبت نشده'}
                    </div>
                  </>
                )}
              </div>
            )
          })}
          {(d.ongoing || []).length === 0 && <div className="empty">کارآموزی در جریانی وجود ندارد.</div>}
        </div>
      </div>
    </>
  )
}
