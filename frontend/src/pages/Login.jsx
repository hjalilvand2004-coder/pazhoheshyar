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

  useEffect(() => { api('/auth/sso/config').then(setSso).catch(() => {}) }, [])

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
      <form className="login-card" onSubmit={submit}>
        <div className="logo">پژوهشیار۳۶۰</div>
        <div className="sub">بازار اتصال پژوهشی — عضو اکوسیستم دانشجو۳۶۰</div>
        {error && <div className="error-box">{error}</div>}
        <label className="fld">نام کاربری</label>
        <input value={username} onChange={e => setUsername(e.target.value)} autoFocus required dir="ltr" style={{ textAlign: 'left' }} />
        <label className="fld">رمز عبور</label>
        <input type="password" value={password} onChange={e => setPassword(e.target.value)} required dir="ltr" style={{ textAlign: 'left' }} />
        <button className="btn" style={{ width: '100%', marginTop: 16, justifyContent: 'center' }} disabled={busy}>
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
  )
}
