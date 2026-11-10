import React, { createContext, useContext, useEffect, useState } from 'react'
import { api, setToken, getToken } from './api.js'

const AuthCtx = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  const refresh = async () => {
    if (!getToken()) { setUser(null); setLoading(false); return }
    try { setUser(await api('/auth/me')) } catch { setUser(null) }
    setLoading(false)
  }

  useEffect(() => {
    refresh()
    const onUnauthorized = () => setUser(null)
    window.addEventListener('py:unauthorized', onUnauthorized)
    return () => window.removeEventListener('py:unauthorized', onUnauthorized)
  }, [])

  const login = async (username, password) => {
    const data = await api('/auth/login', { method: 'POST', body: { username, password } })
    setToken(data.token)
    setUser(data.user)
    return data.user
  }

  const loginWithSsoToken = (token, userData) => {
    setToken(token)
    setUser(userData)
  }

  const logout = async () => {
    let endUrl = ''
    try {
      const d = await api('/auth/logout', { method: 'POST' })
      endUrl = (d && d.end_session_url) || ''
    } catch { /* خروجِ محلی همیشه انجام می‌شود */ }
    setToken('')
    setUser(null)
    return endUrl
  }
  const hasRole = (...roles) => !!(user && (user.roles || []).some(r => roles.includes(r)))

  return (
    <AuthCtx.Provider value={{ user, loading, login, logout, refresh, hasRole, loginWithSsoToken }}>
      {children}
    </AuthCtx.Provider>
  )
}

export const useAuth = () => useContext(AuthCtx)
