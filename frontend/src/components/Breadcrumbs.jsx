import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../auth.jsx'
import { toFa } from '../api.js'

// نقشه مسیرها — برای هر مسیر، زنجیره کامل از خانه تا صفحه جاری ساخته می‌شود
const PROF_ROLES = ['professor', 'research_manager', 'system_admin']

function resolveCrumbs(path, user) {
  const home = { label: 'داشبورد', icon: '🏠', to: '/' }
  const prof = (user?.roles || []).some(r => PROF_ROLES.includes(r))

  if (path === '/') return [{ label: 'داشبورد', icon: '🏠' }]
  if (path.startsWith('/admin/sso')) return [home, { label: 'داشبورد مدیریت پژوهش', icon: '📊', to: '/admin' }, { label: 'تنظیمات ورود یکپارچه', icon: '🔐' }]
  if (path.startsWith('/admin')) return [home, { label: 'داشبورد مدیریت پژوهش', icon: '📊' }]
  if (path === '/requests/new') return [home, { label: 'ثبت درخواست پژوهش', icon: '✍️' }]
  let m = path.match(/^\/requests\/(\d+)/)
  if (m) {
    return prof
      ? [home, { label: 'استخر پژوهشی', icon: '🌊', to: '/pool' }, { label: `درخواست #${toFa(m[1])}`, icon: '📄' }]
      : [home, { label: `درخواست پژوهش #${toFa(m[1])}`, icon: '📄' }]
  }
  if (path.startsWith('/pool')) return [home, { label: 'استخر پژوهشی', icon: '🌊' }]
  if (path.startsWith('/topics')) return [home, { label: 'بانک موضوعات', icon: '📚' }]
  if (path.startsWith('/chat')) return [home, { label: 'گفت‌وگوها', icon: '💬' }]
  m = path.match(/^\/projects\/(\d+)/)
  if (m) return [home, { label: 'پروژه‌های من', icon: '🗂️', to: '/projects' }, { label: `پروژه #${toFa(m[1])}`, icon: '🚀' }]
  if (path.startsWith('/projects')) return [home, { label: 'پروژه‌های من', icon: '🗂️' }]
  if (path.startsWith('/ai')) return [home, { label: 'دستیار هوشمند', icon: '🤖' }]
  if (path.startsWith('/profile')) return [home, { label: 'پروفایل پژوهشی', icon: '👤' }]
  return [home, { label: 'صفحه جاری', icon: '🔎' }]
}

export default function Breadcrumbs() {
  const loc = useLocation()
  const { user } = useAuth()
  const crumbs = resolveCrumbs(loc.pathname, user)
  return (
    <nav className="crumbs" aria-label="مسیر جاری" key={loc.pathname}>
      {crumbs.map((c, i) => (
        <React.Fragment key={i}>
          {i > 0 && <span className="crumb-sep" aria-hidden="true">‹</span>}
          {c.to
            ? <Link className="crumb" to={c.to}>{c.icon} {c.label}</Link>
            : <span className="crumb current" aria-current="page">{c.icon} {c.label}</span>}
        </React.Fragment>
      ))}
    </nav>
  )
}
