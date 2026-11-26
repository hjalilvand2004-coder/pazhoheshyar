import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth.jsx'
import { api } from '../api.js'

export default function Login() {
  const { login } = useAuth()
  const nav = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [sso, setSso] = useState({ enabled: false })
  const [light, setLight] = useState(() => document.documentElement.classList.contains('light-theme'))

  useEffect(() => { api('/auth/sso/config').then(setSso).catch(() => {}) }, [])

  const toggleTheme = () => {
    const isLight = document.documentElement.classList.toggle('light-theme')
    try { localStorage.setItem('theme', isLight ? 'light' : 'dark') } catch { /* حالت شب پیش‌فرض */ }
    setLight(isLight)
  }

  const submit = async (e) => {
    e.preventDefault()
    setError(''); setBusy(true)
    try {
      await login(username.trim().toLowerCase(), password)
      nav('/')
    } catch (err) {
      setError(err.message)
    } finally { setBusy(false) }
  }

  return (
    <div className="login-wrap">
      <button className="theme-toggle" onClick={toggleTheme} aria-label="تغییر تم شب و روز"
              style={{ position: 'absolute', top: 18, left: 18, zIndex: 20 }}>
        <span aria-hidden="true">{light ? '🌙' : '☀️'}</span>
        <span>{light ? 'حالت شب' : 'حالت روز'}</span>
      </button>
      <div className="auth-card">
        <div className="auth-panel">
          <div className="feat-logo">🎓</div>
          <h2>پژوهشیار۳۶۰</h2>
          <div className="tagline">بازار اتصال پژوهشی اکوسیستم دانشجو۳۶۰</div>
          <div className="feat"><div className="fic">🌊</div><div><b>استخر پژوهشی</b><span>ایدهٔ پژوهشی شما را با استاد مناسب متصل می‌کند</span></div></div>
          <div className="feat"><div className="fic">🤖</div><div><b>دستیار هوشمند</b><span>تحلیل استعداد، پیشنهاد موضوع و مجله</span></div></div>
          <div className="feat"><div className="fic">📚</div><div><b>بانک موضوعات</b><span>موضوعات و الگوهای استاندارد اساتید</span></div></div>
          <div className="feat"><div className="fic">🔐</div><div><b>ورود یکپارچه</b><span>با همان حساب پرتال دانشجویار، بدون رمز جدید</span></div></div>
        </div>
        <form className="login-card" onSubmit={submit}>
          <div className="logo">پژوهشیار۳۶۰</div>
          <div className="sub">بازار اتصال پژوهشی — عضو اکوسیستم دانشجو۳۶۰</div>
          {error && <div className="error-box">{error}</div>}
          <label className="fld">نام کاربری</label>
          <input value={username} onChange={e => setUsername(e.target.value)} autoFocus required dir="ltr" style={{ textAlign: 'left' }} />
          <label className="fld">رمز عبور</label>
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} required dir="ltr" style={{ textAlign: 'left' }} />
          <button className="btn" style={{ width: '100%', marginTop: 18, justifyContent: 'center' }} disabled={busy}>
            {busy ? 'در حال ورود…' : 'ورود'}
          </button>
          <div className="divider">ورود یکپارچه سازمانی</div>
          <button
            type="button" className="btn secondary" style={{ width: '100%', justifyContent: 'center' }}
            disabled={!sso.enabled}
            onClick={() => { window.location.assign('/api/v1/auth/sso/login') }}
            title={sso.enabled ? 'ورود با حساب پرتال سازمانی (SSO)' : 'ورود یکپارچه هنوز فعال نشده است'}
          >
            🏫 {sso.button_label || 'ورود با حساب دانشگاهی (SSO)'}
          </button>
          {!sso.enabled && <div className="hint" style={{ marginTop: 6, textAlign: 'center' }}>{sso.message || 'وضعیت SSO نامشخص'}</div>}
          <div className="demo-accounts">
            <b>حساب‌های داده آزمایشی</b> (رمز همه: <code>12345678</code>)<br />
            دانشجو: <code>student1</code> ، <code>student2</code> — استاد: <code>prof1</code> ، <code>prof2</code><br />
            مدیر پژوهش: <code>manager1</code> — مدیر سامانه: <code>admin1</code>
          </div>
        </form>
      </div>
    </div>
  )
}
