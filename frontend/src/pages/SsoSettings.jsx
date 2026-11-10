import React, { useEffect, useState } from 'react'
import { useAuth } from '../auth.jsx'
import { api } from '../api.js'

const CLIENT_SNIPPET = `{
  "pazhoheshyar360": {
    "name": "پژوهشیار۳۶۰",
    "confidential": false,
    "redirect_uris": [
      "http://آدرس-این-سامانه/sso/callback"
    ],
    "post_logout_redirect_uris": [
      "http://آدرس-این-سامانه/?loggedOut=1"
    ]
  }
}`

const EMPTY = {
  enabled: false, issuer: 'http://188.212.96.235:8086', client_id: 'pazhoheshyar360',
  client_type: 'public', client_secret: '',
  redirect_uri: window.location.origin + '/sso/callback',
  post_logout_redirect_uri: window.location.origin + '/?loggedOut=1',
  button_label: 'ورود با حساب پرتال دانشجویار۳۶۰',
  scope: 'openid profile email',
  auto_create_users: true, default_roles: ['student'],
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
    if (s.enabled && (!(s.issuer || '').trim() || !(s.client_id || '').trim() || !(s.redirect_uri || '').trim())) {
      setErr('برای فعال‌سازی، Issuer و Client ID و Redirect URI را کامل کنید.')
      return
    }
    if (s.enabled && s.client_type === 'confidential' && !s.client_secret && !s.client_secret_set) {
      setErr('برای کلاینت محرمانه (confidential) مقدار Client Secret الزامی است؛ برای پرتال دانشجویار۳۶۰ نوع public را انتخاب کنید.')
      return
    }
    try {
      const d = await api('/admin/sso/settings', { method: 'PUT', body: s })
      setS({ ...d, client_secret: '' })
      setMsg(s.enabled
        ? 'تنظیمات ذخیره و ورود یکپارچه فعال شد (در فایل آینه هم پایدار شد).'
        : 'تنظیمات SSO ذخیره شد (ورود یکپارچه غیرفعال است).')
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
        <h3>⚙️ تنظیمات ورود یکپارچه (پرتال دانشجویار۳۶۰ / OIDC)</h3>
        <div className="hint">
          جریان استاندارد <b>Authorization Code + PKCE (S256)</b>؛ تبادل کد و اعتبارسنجی id_token (RS256، iss/aud/nonce) کاملاً در بک‌اند انجام می‌شود.
          هویت با <code>issuer + sub</code> به حساب محلی متصل می‌شود و نقش‌ها همیشه در بک‌اند کنترل می‌شوند.
        </div>
        <label style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 10 }}>
          <input type="checkbox" style={{ width: 'auto' }} checked={s.enabled} onChange={set('enabled')} />
          فعال‌سازی ورود یکپارچه (دکمهٔ SSO با برچسب زیر در صفحه ورود نمایش داده می‌شود)
        </label>
        <label className="fld">برچسب دکمهٔ ورود</label>
        <input value={s.button_label || ''} onChange={set('button_label')} />
        <label className="fld">Issuer — دقیقاً بدون اسلش انتهایی (پورت ۸۰۸۶، نه ۸۰۸۰!)</label>
        <input dir="ltr" style={{ textAlign: 'left' }} value={s.issuer} onChange={set('issuer')} />
        <div className="grid cols-2">
          <div>
            <label className="fld">Client ID (ثبت‌شده در clients.json پرتال)</label>
            <input dir="ltr" style={{ textAlign: 'left' }} value={s.client_id} onChange={set('client_id')} />
          </div>
          <div>
            <label className="fld">نوع کلاینت</label>
            <select dir="ltr" style={{ textAlign: 'left' }} value={s.client_type || 'public'} onChange={set('client_type')}>
              <option value="public">public — با PKCE، بدون Secret (پرتال دانشجویار۳۶۰)</option>
              <option value="confidential">confidential — با Client Secret</option>
            </select>
          </div>
          {s.client_type === 'confidential' && (
            <div>
              <label className="fld">Client Secret {s.client_secret_set ? '(ثبت‌شده — خالی بگذارید تا تغییر نکند)' : ''}</label>
              <input dir="ltr" style={{ textAlign: 'left' }} type="password" value={s.client_secret} onChange={set('client_secret')} />
            </div>
          )}
          <div>
            <label className="fld">Redirect URI — باید کاراکتربه‌کاراکتر در clients.json پرتال ثبت شود</label>
            <input dir="ltr" style={{ textAlign: 'left' }} value={s.redirect_uri} onChange={set('redirect_uri')} />
          </div>
          <div>
            <label className="fld">Post-Logout Redirect URI (بازگشت پس از خروج)</label>
            <input dir="ltr" style={{ textAlign: 'left' }} value={s.post_logout_redirect_uri || ''} onChange={set('post_logout_redirect_uri')} />
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
        <div className="hint" style={{ marginTop: 6 }}>
          نقش‌ها در هر ورود: اگر در claim <code>resource_access["{s.client_id}"].roles</code> نقشی با پسوند <code>.admin</code> باشد ← مدیر سامانه؛
          در غیر این صورت نقش‌های پیش‌فرض. حساب‌های موجود هم‌نام با <code>preferred_username</code> خودکار متصل می‌شوند.
        </div>
        <div className="row" style={{ marginTop: 14 }}>
          <button className="btn" onClick={save}>ذخیره تنظیمات</button>
          <button className="btn secondary" onClick={test}>🔌 تست اتصال به پرتال (Discovery + JWKS)</button>
        </div>
        {testResult && (
          <>
            <div className={testResult.ok ? 'ok-box' : 'error-box'}>{testResult.message}</div>
            {testResult.provider && testResult.ok && (
              <div className="hint" dir="ltr" style={{ textAlign: 'left', fontSize: 12.5 }}>
                issuer: {testResult.provider.issuer_reported}<br />
                authorize: {testResult.provider.authorization_endpoint}<br />
                token: {testResult.provider.token_endpoint}<br />
                userinfo: {testResult.provider.userinfo_endpoint}<br />
                jwks: {testResult.provider.jwks_uri} ({testResult.jwks_keys} keys)<br />
                end_session: {testResult.provider.end_session_endpoint}
              </div>
            )}
          </>
        )}
        {s.last_test_status && !testResult && <div className="hint">آخرین تست: {s.last_test_status}</div>}
      </div>

      <div className="card">
        <h3>راهنمای گام‌به‌گام اتصال به پرتال دانشجویار۳۶۰</h3>
        <ol style={{ paddingRight: 20, fontSize: 13.5, lineHeight: 1.9 }}>
          <li><b>بررسی سلامت پرتال:</b> <code dir="ltr">GET http://188.212.96.235:8086/healthz</code> باید <code dir="ltr">{`{"status":"ok"}`}</code> بدهد. اگر پاسخ نداد، سرویس پرتال خاموش است — روی سرور پرتال <code dir="ltr">RUN-PORTAL.bat</code> را اجرا کنید.</li>
          <li><b>ثبت client این سامانه در پرتال:</b> از مدیر SSO بخواهید کلید زیر را در فایل <code dir="ltr">data/clients.json</code> پرتال اضافه و پرتال را یک‌بار ری‌استارت کند:</li>
        </ol>
        <pre dir="ltr" style={{ background: '#f4f6fb', padding: 12, borderRadius: 8, fontSize: 12.5, overflowX: 'auto', textAlign: 'left' }}>{CLIENT_SNIPPET}</pre>
        <ol start={3} style={{ paddingRight: 20, fontSize: 13.5, lineHeight: 1.9 }}>
          <li><b>Redirect URI را دقیق کنید:</b> مقدار «Redirect URI» فرم بالا باید با آنچه در clients.json ثبت شده کاراکتربه‌کاراکتر یکی باشد (http/https، پورت، اسلش). با تغییر آدرس استقرار سامانه، هر دو طرف را هم‌زمان اصلاح کنید.</li>
          <li><b>ذخیره و تست:</b> تیک فعال‌سازی را بزنید، «ذخیره تنظیمات» و سپس «تست اتصال» را بزنید — Discovery و JWKS واقعی پرتال خوانده و تعداد کلیدها گزارش می‌شود.</li>
          <li><b>اتصال حساب‌های موجود:</b> هر کاربر از «پروفایل ← حساب دانشگاهی (SSO)» هویت پرتال را به حسابش متصل می‌کند؛ حساب‌های هم‌نام با نام کاربری پرتال در اولین ورود خودکار وصل می‌شوند.</li>
        </ol>
        <div className="hint">
          اگر کاربران بیرونی پرتال را باز نمی‌کنند: <code dir="ltr">OPEN-FIREWALL.bat</code> را روی سرور پرتال اجرا کنید (TCP 8086 در فایروال ویندوز و Security Group).
          خطای «connection refused» یعنی سرویس پرتال اجرا نیست.
        </div>
        <div className="hint">
          حساب‌های آزمون پرتال: <code dir="ltr">m.ahmadi / Student@360</code> (دانشجو)، <code dir="ltr">s.hosseini / Staff@360</code> (کارمند)، <code dir="ltr">admin / Admin@360</code> (مدیر پرتال) — در محیط واقعی رمزها عوض شود.
        </div>
      </div>
    </>
  )
}
