import React, { useEffect, useState } from 'react'
import { useAuth } from '../auth.jsx'
import { api } from '../api.js'

const EMPTY = {
  enabled: false, issuer: '', client_id: 'pajoohesh-yar360', client_secret: '',
  redirect_uri: window.location.origin + '/sso/callback', scope: 'openid profile email',
  auto_create_users: false, default_roles: ['student'],
}

export default function SsoSettings() {
  const { hasRole } = useAuth()
  const [s, setS] = useState(null)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [testResult, setTestResult] = useState(null)

  useEffect(() => { api('/admin/sso/settings').then(d => setS({ ...EMPTY, ...d, client_secret: '' })).catch(e => setErr(e.message)) }, [])
  if (!hasRole('system_admin')) return <div className="empty">فقط مدیر سامانه به تنظیمات SSO دسترسی دارد.</div>
  if (!s) return <div className="empty">در حال بارگذاری…</div>

  const set = (k) => (e) => setS({ ...s, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const toggleRole = (r) => setS(prev => ({
    ...prev,
    default_roles: prev.default_roles.includes(r) ? prev.default_roles.filter(x => x !== r) : [...prev.default_roles, r],
  }))

  const save = async () => {
    setMsg(''); setErr('')
    try {
      const d = await api('/admin/sso/settings', { method: 'PUT', body: s })
      setS({ ...d, client_secret: '' })
      setMsg('تنظیمات SSO ذخیره شد.')
    } catch (e) { setErr(e.message) }
  }
  const test = async () => {
    setTestResult(null)
    try { setTestResult(await api('/admin/sso/test', { method: 'POST' })) } catch (e) { setErr(e.message) }
  }

  return (
    <>
      {msg && <div className="ok-box">{msg}</div>}
      {err && <div className="error-box">{err}</div>}
      <div className="card">
        <h3>⚙️ تنظیمات ورود یکپارچه (Keycloak / OIDC)</h3>
        <div className="hint">
          هویت مرکزی با <code>issuer + sub</code> به حساب محلی متصل می‌شود. نقش‌ها و مجوزها همیشه در بک‌اند بررسی می‌شوند.
        </div>
        <label style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 10 }}>
          <input type="checkbox" style={{ width: 'auto' }} checked={s.enabled} onChange={set('enabled')} />
          فعال‌سازی ورود یکپارچه (دکمه SSO در صفحه ورود نمایش داده می‌شود)
        </label>
        <label className="fld">Issuer (مثال: https://sso.university.ac.ir/realms/daneshjoo360)</label>
        <input dir="ltr" style={{ textAlign: 'left' }} value={s.issuer} onChange={set('issuer')} />
        <div className="grid cols-2">
          <div>
            <label className="fld">Client ID</label>
            <input dir="ltr" style={{ textAlign: 'left' }} value={s.client_id} onChange={set('client_id')} />
          </div>
          <div>
            <label className="fld">Client Secret {s.client_secret_set ? '(ثبت‌شده — خالی بگذارید تا تغییر نکند)' : ''}</label>
            <input dir="ltr" style={{ textAlign: 'left' }} type="password" value={s.client_secret} onChange={set('client_secret')} />
          </div>
          <div>
            <label className="fld">Redirect URI (در Keycloak ثبت شود)</label>
            <input dir="ltr" style={{ textAlign: 'left' }} value={s.redirect_uri} onChange={set('redirect_uri')} />
          </div>
          <div>
            <label className="fld">Scope</label>
            <input dir="ltr" style={{ textAlign: 'left' }} value={s.scope} onChange={set('scope')} />
          </div>
        </div>
        <label style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 10 }}>
          <input type="checkbox" style={{ width: 'auto' }} checked={s.auto_create_users} onChange={set('auto_create_users')} />
          ایجاد خودکار حساب برای کاربران جدید SSO با نقش‌های پیش‌فرض:
          {['student', 'professor'].map(r => (
            <label key={r} style={{ display: 'inline-flex', gap: 4, alignItems: 'center', marginInlineStart: 8 }}>
              <input type="checkbox" style={{ width: 'auto' }} checked={s.default_roles.includes(r)} onChange={() => toggleRole(r)} />
              {r === 'student' ? 'دانشجو' : 'استاد'}
            </label>
          ))}
        </label>
        <div className="row" style={{ marginTop: 14 }}>
          <button className="btn" onClick={save}>ذخیره تنظیمات</button>
          <button className="btn secondary" onClick={test}>🔌 تست اتصال به سرور هویت</button>
        </div>
        {testResult && (
          <div className={testResult.ok ? 'ok-box' : 'error-box'}>{testResult.message}</div>
        )}
        {s.last_test_status && !testResult && <div className="hint">آخرین تست: {s.last_test_status}</div>}
      </div>

      <div className="card">
        <h3>راهنمای گام‌به‌گام Keycloak</h3>
        <ol style={{ paddingRight: 20, fontSize: 13.5 }}>
          <li>در Keycloak یک Realm بسازید (مثال <code>daneshjoo360</code>).</li>
          <li>Clients ← Create: شناسه <code>pajoohesh-yar360</code>، نوع <code>openid-connect</code>.</li>
          <li>Valid Redirect URIs را دقیقاً برابر مقدار Redirect URI همین صفحه قرار دهید (مثال <code>http://SERVER:8000/sso/callback</code>).</li>
          <li>در تب Credentials، Client Secret را کپی و در همین فرم وارد کنید.</li>
          <li>Issuer را برابر <code>https://سرور-کی‌کلوک/realms/daneshjoo360</code> تنظیم و ذخیره کنید، سپس «تست اتصال» را بزنید.</li>
          <li>برای اتصال حساب‌های موجود، کاربر ابتدا با نام کاربری وارد شود؛ ورود SSO بعدی هویت را به‌صورت خودکار به حساب متصل می‌کند.</li>
        </ol>
        <div className="hint">توجه: سامانه‌های دیگر اکوسیستم (برنامه‌یار۳۶۰، درسیار۳۶۰ و …) با همان Realm مشترک، ورود یکپارچه دارند.</div>
      </div>
    </>
  )
}
