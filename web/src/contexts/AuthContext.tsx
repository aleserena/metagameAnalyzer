import { createContext, useCallback, useContext, useEffect, useState } from 'react'

const STORAGE_KEY = 'admin_token'
const API_BASE = '/api'

type User = 'admin' | null

interface AuthContextValue {
  user: User
  loading: boolean
  login: (password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User>(null)
  const [loading, setLoading] = useState(true)

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY)
    setUser(null)
  }, [])

  useEffect(() => {
    const token = localStorage.getItem(STORAGE_KEY)
    if (!token) {
      setLoading(false)
      return
    }
    fetch(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => {
        if (res.ok) {
          setUser('admin')
        } else {
          localStorage.removeItem(STORAGE_KEY)
        }
      })
      .catch(() => localStorage.removeItem(STORAGE_KEY))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const handler = () => logout()
    window.addEventListener('auth-logout', handler)
    return () => window.removeEventListener('auth-logout', handler)
  }, [logout])

  const login = useCallback(
    async (password: string) => {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(err.detail || res.statusText)
      }
      const data = await res.json()
      if (data.token) {
        localStorage.setItem(STORAGE_KEY, data.token)
        setUser('admin')
      }
    },
    []
  )

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

export function getToken(): string | null {
  return localStorage.getItem(STORAGE_KEY)
}
