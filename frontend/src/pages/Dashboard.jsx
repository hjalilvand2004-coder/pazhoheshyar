import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth.jsx'
import { api, REQ_STATUS, STATUS_BADGE, fmtDateTime } from '../api.js'

function StatTile({ icon, bg, label, num }) {
  return (
    <div className="stat-tile">
      <div className="ic" style={bg ? { background: bg } : undefined}>{icon}</div>
      <div>
        <div className="num">{num ?? '—'}</div>
        <div className="lbl">{label}</div>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const { user, hasRole } = useAuth()
  const [mine, setMine] = useState([])
  const [projects, setProjects] = useState([])
  const [offers, setOffers] = useState([])
  const [metrics, setMetrics] = useState(null)

  useEffect(() => {
    if (hasRole('student')) api('/requests/mine').then(setMine).catch(() => {})
    if (hasRole('professor')) api('/offers/mine').then(setOffers).catch(() => {})
    api('/projects/mine').then(setProjects).catch(() => {})
    if (hasRole('research_manager', 'system_admin')) api('/admin/metrics').then(setMetrics).catch(() => {})
  }, [])

  const nextAction = (r) => {
    switch (r.status) {
      case 'draft': return 'اقدام بعدی: انتشار درخواست در استخر پژوهشی'
      case 'published': return 'اقدام بعدی: منتظر اعلام آمادگی اساتید بمانید'
      case 'offers_received': return 'اقدام بعدی: پیشنهادها را ببینید و گفت‌وگو را آغاز کنید'
      case 'negotiating': return 'اقدام بعدی: انتخاب نهایی استاد و پذیرش پیشنهاد'
      case 'initial_agreement': return 'اقدام بعدی: امضای توافق‌نامه همکاری'
      case 'pending_university_approval': return 'اقدام بعدی: پیگیری تأیید دانشگاه'
      case 'connected_to_project': return 'پروژه تشکیل شد — به فضای پروژه بروید'
      default: return r.closed_reason || 'این درخواست بسته است'
    }
  }

  return (
    <>
      <div className="dash-hero">
        <span className="deco d1">✨</span>
        <span className="deco d2">📚</span>
        <span className="deco d3">🚀</span>
        <div className="dash-hero-in">
          <div className="icon-big">👋</div>
          <div>
            <h2>سلام {user.display_name}</h2>
            <p>
              نقش‌های شما: {user.role_labels?.join('، ')} — پژوهشیار۳۶۰ کشف استعداد پژوهشی، اتصال دانشجو و استاد
              و مدیریت مسیر پژوهش تا انتشار را ممکن می‌کند.
            </p>
            <div className="hero-actions">
              {hasRole('student') && (
                <>
                  <Link className="btn hero-btn solid" to="/requests/new">➕ ثبت درخواست پژوهش</Link>
                  <Link className="btn hero-btn" to="/topics">📚 بانک موضوعات اساتید</Link>
                  <Link className="btn hero-btn" to="/ai">🤖 دستیار هوشمند</Link>
                </>
              )}
              {hasRole('professor') && (
                <>
                  <Link className="btn hero-btn solid" to="/pool">🔍 استخر پژوهشی</Link>
                  <Link className="btn hero-btn" to="/topics">📢 انتشار موضوع/الگوی استاندارد</Link>
                </>
              )}
              {hasRole('research_manager') && (
                <Link className="btn hero-btn solid" to="/admin">📊 داشبورد مدیریت پژوهش</Link>
              )}
              {hasRole('system_admin') && (
                <>
                  <Link className="btn hero-btn solid" to="/admin/sso">⚙️ تنظیمات ورود یکپارچه (SSO)</Link>
                  <Link className="btn hero-btn" to="/admin">📊 شاخص‌ها</Link>
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      {metrics && (
        <div className="stats-strip">
          <StatTile icon="🗂️" bg="var(--sky-light)" label="کل درخواست‌ها" num={metrics.requests_total} />
          <StatTile icon="🚀" label="پروژه‌های فعال" num={metrics.projects_active} />
          <StatTile icon="📨" bg="var(--amber-light)" label="اعلام‌های آمادگی فعال" num={metrics.offers_active} />
          <StatTile icon="👨‍🏫" bg="var(--violet-light)" label="اساتید همکار" num={metrics.professors} />
        </div>
      )}

      {hasRole('student') && (
        <div className="card">
          <h3>درخواست‌های من و اقدام بعدی</h3>
          {mine.length === 0 && <div className="empty">هنوز درخواستی ثبت نکرده‌اید.</div>}
          {mine.map(r => (
            <div key={r.id} className="card" style={{ marginBottom: 10 }}>
              <div className="row">
                <b style={{ flex: 2 }}><Link to={`/requests/${r.id}`}>{r.title}</Link></b>
                <span className={`badge ${STATUS_BADGE[r.status]}`}>{REQ_STATUS[r.status]}</span>
                <span className="hint">{fmtDateTime(r.updated_at)}</span>
              </div>
              <div className="hint">{nextAction(r)}</div>
            </div>
          ))}
        </div>
      )}

      {hasRole('professor') && (
        <div className="card">
          <h3>اعلام‌های آمادگی من</h3>
          {offers.length === 0 && <div className="empty">از استخر پژوهشی، درخواست‌ها را ببینید و آمادگی اعلام کنید.</div>}
          <table className="tbl">
            <tbody>
              {offers.map(o => (
                <tr key={o.id}>
                  <td><Link to={`/requests/${o.request_id}`}>{o.request_title}</Link></td>
                  <td><span className="badge">{o.status && (o.status === 'sent' ? 'ارسال‌شده' : o.status === 'in_dialogue' ? 'در گفت‌وگو' : o.status === 'accepted' ? 'پذیرفته‌شده' : o.status === 'converted_to_project' ? 'تبدیل به پروژه' : o.status === 'superseded' ? 'جایگزین‌شده' : o.status === 'withdrawn' ? 'پس‌گرفته‌شده' : o.status === 'rejected_by_student' ? 'ردشده' : o.status)}</span></td>
                  <td className="hint">{fmtDateTime(o.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card">
        <h3>پروژه‌های من</h3>
        {projects.length === 0 && <div className="empty">پروژه فعالی ندارید.</div>}
        {projects.map(p => (
          <div key={p.id} className="row" style={{ borderBottom: '1px solid var(--border)', padding: '6px 0' }}>
            <b style={{ flex: 2 }}><Link to={`/projects/${p.id}`}>{p.title}</Link></b>
            <span className={`badge ${p.status === 'active' ? 'green' : 'gray'}`}>{p.status === 'active' ? 'فعال' : p.status === 'closing' ? 'در حال خاتمه' : 'خاتمه‌یافته'}</span>
            <span className="hint">{p.lead_professor_name}</span>
          </div>
        ))}
      </div>
    </>
  )
}
