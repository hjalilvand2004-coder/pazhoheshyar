import React, { useEffect, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth.jsx'
import { api, fmtDateTime } from '../api.js'
import Breadcrumbs from './Breadcrumbs.jsx'

function Bell() {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState([])
  const [unread, setUnread] = useState(0)

  const load = async () => {
    try {
      const c = await api('/notifications/count')
      setUnread(c.unread)
      if (open) setItems(await api('/notifications?limit=30'))
    } catch { /* بی‌اهمیت */ }
  }

  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t) }, [open])

  const openItem = async (n) => {
    if (!n.is_read) { await api(`/notifications/${n.id}/read`, { method: 'POST' }).catch(() => {}) }
    setOpen(false)
    if (n.link) window.location.hash = ''
    if (n.link) window.location.assign(n.link)
  }

  return (
    <div style={{ position: 'relative' }}>
      <button className="bell" onClick={() => setOpen(o => !o)} aria-label="اعلان‌ها">
        🔔{unread > 0 && <span className="cnt">{unread}</span>}
      </button>
      {open && (
        <div className="notif-panel">
          <div className="row" style={{ padding: '4px 8px' }}>
            <b>اعلان‌ها</b>
            <button className="btn ghost small" onClick={async () => { await api('/notifications/read-all', { method: 'POST' }); load() }}>
              خواندن همه
            </button>
          </div>
          {items.length === 0 && <div className="empty">اعلانی نیست</div>}
          {items.map(n => (
            <div key={n.id} className={`notif-item ${n.is_read ? '' : 'unread'}`} onClick={() => openItem(n)}>
              <b>{n.title}</b>
              <div className="hint">{n.body}</div>
              <div className="hint">{fmtDateTime(n.created_at)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const MENUS = [
  { to: '/', label: 'داشبورد', ic: '🏠', roles: ['student', 'professor', 'research_manager', 'system_admin'], end: true },
  { to: '/requests/new', label: 'ثبت درخواست پژوهش', ic: '✍️', roles: ['student'] },
  { to: '/pool', label: 'استخر پژوهشی', ic: '🌊', roles: ['professor', 'research_manager', 'system_admin'] },
  { to: '/topics', label: 'بانک موضوعات', ic: '📚', roles: ['student', 'professor', 'research_manager', 'system_admin'] },
  { to: '/chat', label: 'گفت‌وگوها', ic: '💬', roles: ['student', 'professor'] },
  { to: '/projects', label: 'پروژه‌های من', ic: '🗂️', roles: ['student', 'professor', 'research_manager', 'system_admin'] },
  { to: '/research', label: 'فضای پژوهش', ic: '📝', roles: ['student', 'professor', 'research_manager', 'system_admin'] },
  { to: '/internship', label: 'کارآموزی', ic: '🏭', adaptive: true, roles: ['student', 'professor', 'research_manager', 'system_admin'] },
  { to: '/internship-dashboard', label: 'گزارش کارآموزی‌ها', ic: '📈', roles: ['research_manager', 'system_admin'] },
  { to: '/practicum', label: 'درس‌پروژه و تحقیق و ارائه', ic: '🛠️', adaptive: true, roles: ['student', 'professor', 'research_manager', 'system_admin'] },
  { to: '/lab', label: 'آزمایشگاه شبیه‌سازی', ic: '🧪', roles: ['student', 'professor', 'research_manager', 'system_admin'] },
  { to: '/ai', label: 'دستیار هوشمند', ic: '🤖', roles: ['student', 'professor', 'research_manager'] },
  { to: '/semantic', label: 'شبکهٔ دانش', ic: '🕸️', roles: ['student', 'professor', 'research_manager', 'system_admin'] },
  { to: '/admin', label: 'داشبورد مدیریت پژوهش', ic: '📊', roles: ['research_manager', 'system_admin'] },
  { to: '/admin/sso', label: 'تنظیمات ورود یکپارچه', ic: '🔐', roles: ['system_admin'] },
  { to: '/profile', label: 'پروفایل پژوهشی', ic: '👤', roles: ['student', 'professor', 'research_manager', 'system_admin'] },
]

/* برچسب منوی درس‌های عملی نسبت به مقطع و نقش — دو صفحهٔ جدا: کارآموزی / درس‌پروژه و تحقیق و ارائه */
function internshipLabel(user) {
  const roles = user?.roles || []
  if (roles.includes('professor')) return 'ارزیابی کارآموزی'
  if (roles.includes('research_manager') || roles.includes('system_admin')) return 'کارآموزی دانشجویان'
  return 'کارآموزی'
}

function projectLabel(user) {
  const roles = user?.roles || []
  if (roles.includes('professor')) return 'ارزیابی درس‌پروژه و تحقیق'
  if (roles.includes('research_manager') || roles.includes('system_admin')) return 'درس‌پروژه و تحقیق دانشجویان'
  if (user?.degree_key === 'master') return 'تحقیق و ارائه'
  return 'درس‌پروژه'
}

function ThemeToggle() {
  const [light, setLight] = useState(() => document.documentElement.classList.contains('light-theme'))
  const toggle = () => {
    const isLight = document.documentElement.classList.toggle('light-theme')
    try { localStorage.setItem('theme', isLight ? 'light' : 'dark') } catch { /* حالت شب پیش‌فرض */ }
    window.dispatchEvent(new Event('py:theme'))
    setLight(isLight)
  }
  return (
    <button className="theme-toggle" onClick={toggle} aria-label="تغییر تم شب و روز"
            title="تغییر تم شب / روز">
      <span aria-hidden="true">{light ? '🌙' : '☀️'}</span>
      <span>{light ? 'حالت شب' : 'حالت روز'}</span>
    </button>
  )
}

export default function Layout({ children }) {
  const { user, logout } = useAuth()
  const nav = useNavigate()
  const loc = useLocation()

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="logo-chip">🎓</span>
          <span>پژوهشیار۳۶۰<small>اکوسیستم دانشجو۳۶۰</small></span>
        </div>
        <div className="nav-cap">منوی اصلی</div>
        {MENUS
          .map(m => (m.to === '/internship' ? { ...m, label: internshipLabel(user) }
            : m.to === '/practicum' ? { ...m, label: projectLabel(user) } : m))
          .filter(m => m.roles.some(r => (user.roles || []).includes(r)))
          .map(m => (
            <NavLink key={m.to} to={m.to} end={m.end} className={({ isActive }) => (isActive ? 'active' : '')}>
              <span className="ic">{m.ic}</span>
              {m.label}
            </NavLink>
          ))}
        <div className="spacer" />
        <div className="userbox">
          <span className="avatar">{(user.display_name || '؟').trim().charAt(0)}</span>
          <div>
            <b>{user.display_name}</b>
            {user.role_labels?.join('، ')}
            {user.degree && <span className="degree-tag">🎓 {user.degree}</span>}
            {user.sso_linked && <div className="sso-tag">🔗 متصل به SSO</div>}
          </div>
        </div>
        <button className="logout" onClick={async () => { const end = await logout(); if (!end) nav('/login') }}>خروج از حساب</button>
      </aside>
      <div className="main">
        <header className="topbar">
          <Breadcrumbs />
          <ThemeToggle />
          <Bell />
        </header>
        <main className="content" key={loc.pathname}>{children}</main>
        <footer className="footer">
          <span>پژوهشیار۳۶۰ — نسخه ۱.۴.۰ | بخشی از اکوسیستم دانشجو۳۶۰ | داده‌های نمایشی صریحاً «آزمایشی» برچسب خورده‌اند</span>
        </footer>
      </div>
    </div>
  )
}
