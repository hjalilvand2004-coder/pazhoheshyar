import React, { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth.jsx'
import { api } from '../api.js'

export default function Callback() {
  const [params] = useSearchParams()
  const nav = useNavigate()
  const { loginWithSsoToken } = useAuth()
  const [error, setError] = useState('')

  useEffect(() => {
    const code = params.get('code')
    const state = params.get('state')
    const error = params.get('error')
    if (!code && !error) { setError('کد بازگشتی از سرور هویت یافت نشد.'); return }
    const qs = error
      ? `error=${encodeURIComponent(error)}`
      : `code=${encodeURIComponent(code)}&state=${encodeURIComponent(state || '')}`
    api(`/auth/sso/callback?${qs}`)
      .then(data => {
        loginWithSsoToken(data.token, data.user)
        nav('/')
      })
      .catch(err => setError(err.message))
  }, [])

  return (
    <div className="login-wrap">
      <div className="login-card" style={{ textAlign: 'center' }}>
        <div className="logo">پژوهشیار۳۶۰</div>
        {error
          ? <><div className="error-box">{error}</div><button className="btn" onClick={() => nav('/login')}>بازگشت به ورود</button></>
          : <div className="sub">در حال تکمیل ورود یکپارچه…</div>}
      </div>
    </div>
  )
}
