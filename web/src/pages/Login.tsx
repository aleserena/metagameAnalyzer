import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function Login() {
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const { login, user } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    if (user === 'admin') navigate('/', { replace: true })
  }, [user, navigate])

  if (user === 'admin') return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(password)
      navigate('/', { replace: true })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="chart-container" style={{ maxWidth: 400, margin: '2rem auto' }}>
      <h1 className="page-title">Admin login</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
        Sign in to access Scrape and Settings.
      </p>
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            autoFocus
            disabled={submitting}
          />
        </div>
        {error && <div className="error" style={{ marginBottom: '1rem' }}>{error}</div>}
        <button type="submit" className="btn" disabled={submitting}>
          {submitting ? 'Signing in...' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
