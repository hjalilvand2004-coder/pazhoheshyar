import React, { useEffect, useState } from 'react'
import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth.jsx'
import { api, fmtDateTime } from '../api.js'

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
  { to: '/', label: 'داشبورد', roles: ['student', 'professor', 'research_manager', 'system_admin'], end: true },
  { to: '/requests/new', label: 'ثبت درخواست پژوهش', roles: ['student'] },
  { to: '/pool', label: 'استخر پژوهشی', roles: ['professor', 'research_manager', 'system_admin'] },
  { to: '/topics', label: 'بانک موضوعات', roles: ['student', 'professor', 'research_manager', 'system_admin'] },
  { to: '/chat', label: 'گفت‌وگوها', roles: ['student', 'professor'] },
  { to: '/projects', label: 'پروژه‌های من', roles: ['student', 'professor', 'research_manager', 'system_admin'] },
  { to: '/ai', label: 'دستیار هوشمند', roles: ['student', 'professor', 'research_manager'] },
  { to: '/admin', label: 'داشبورد مدیریت پژوهش', roles: ['research_manager', 'system_admin'] },
  { to: '/admin/sso', label: 'تنظیمات ورود یکپارچه', roles: ['system_admin'] },
  { to: '/profile', label: 'پروفایل پژوهشی', roles: ['student', 'professor', 'research_manager', 'system_admin'] },
]

export default function Layout({ children }) {
  const { user, logout } = useAuth()
  const nav = useNavigate()
  const loc = useLocation()
  const title = MENUS.find(m => (m.end ? loc.pathname === m.to : loc.pathname.startsWith(m.to)))?.label || 'پژوهشیار۳۶۰'

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">پژوهشیار۳۶۰<small>اکوسیستم دانشجو۳۶۰</small></div>
        {MENUS.filter(m => m.roles.some(r => (user.roles || []).includes(r))).map(m => (
          <NavLink key={m.to} to={m.to} end={m.end} className={({ isActive }) => (isActive ? 'active' : '')}>
            {m.label}
          </NavLink>
        ))}
        <div className="spacer" />
        <div className="userbox">
          <b>{user.display_name}</b>
          {user.role_labels?.join('، ')}
          {user.sso_linked && <div>🔗 متصل به SSO</div>}
        </div>
        <button className="logout" onClick={() => { logout(); nav('/login') }}>خروج از حساب</button>
      </aside>
      <div className="main">
        <header className="topbar">
          <h1>{title}</h1>
          <Bell />
        </header>
        <main className="content">{children}</main>
        <footer className="footer">
          پژوهشیار۳۶۰ — نسخه ۱.۰.۰ | بخشی از اکوسیستم دانشجو۳۶۰ | داده‌های نمایشی صریحاً «آزمایشی» برچسب خورده‌اند
        </footer>
      </div>
    </div>
  )
}
