import { createContext, useContext, useEffect, useState } from 'react'
import api, { refreshAccessToken, setAccessToken } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const raw = localStorage.getItem('user')
    if (!raw) return null
    try {
      return JSON.parse(raw)
    } catch {
      // Corrupted/stale entry (e.g. left over from an earlier app version) --
      // drop it rather than crash the whole app on mount.
      localStorage.removeItem('user')
      return null
    }
  })
  // The access token is in-memory only (see api.js) and doesn't survive a
  // hard reload, so a `user` rehydrated from localStorage is only a
  // rendering hint until a silent refresh against the httpOnly cookie
  // confirms it. `ready` gates protected routes so they don't flash a
  // redirect to /login while that confirmation is in flight.
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function init() {
      if (user) {
        try {
          await refreshAccessToken()
        } catch {
          if (!cancelled) {
            localStorage.removeItem('user')
            setUser(null)
          }
        }
      }
      if (!cancelled) setReady(true)
    }
    init()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once on mount only
  }, [])

  const login = async (email, password) => {
    const form = new URLSearchParams()
    form.append('username', email)
    form.append('password', password)
    const { data } = await api.post('/auth/login', form)
    setAccessToken(data.access_token)
    const u = {
      role: data.role,
      tourist_id: data.tourist_id,
      full_name: data.full_name,
      email,
    }
    localStorage.setItem('user', JSON.stringify(u))
    setUser(u)
    setReady(true)
    return u
  }

  const logout = () => {
    // Best-effort revocation -- fire and forget. The refresh-token cookie is
    // sent automatically (withCredentials); local state is cleared
    // regardless of whether this call succeeds, since the user is leaving
    // either way.
    api.post('/auth/logout', {}).catch(() => {})
    setAccessToken(null)
    localStorage.removeItem('user')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, ready, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
