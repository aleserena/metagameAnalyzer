import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { useAuth } from '../contexts/AuthContext'
import { reportError } from '../utils'

export default function Login() {
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const { login, user } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    if (user === 'admin') navigate('/', { replace: true })
  }, [user, navigate])

  if (user === 'admin') return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErrorMessage(null)
    setSubmitting(true)
    try {
      await login(password)
      toast.success('Signed in successfully')
      navigate('/', { replace: true })
    } catch (e) {
      const msg = reportError(e)
      setErrorMessage(msg)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="chart-container" style={{ maxWidth: 400, margin: '2rem auto' }}>
      <h1 className="page-title">Admin login</h1>
      <form onSubmit={handleSubmit}>
        {errorMessage && (
          <div
            className="form-error"
            role="alert"
            style={{
              marginBottom: '1rem',
              padding: '0.75rem 1rem',
              borderRadius: 'var(--radius)',
              backgroundColor: 'var(--danger-bg, rgba(220, 53, 69, 0.15))',
              color: 'var(--danger, #dc3545)',
            }}
          >
            {errorMessage}
          </div>
        )}
        <div className="form-group">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value)
              setErrorMessage(null)
            }}
            autoComplete="current-password"
            autoFocus
            disabled={submitting}
          />
        </div>
        <button type="submit" className="btn" disabled={submitting}>
          {submitting ? 'Signing in...' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
