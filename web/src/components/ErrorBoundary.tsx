import { Component, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { getErrorMessage } from '../utils'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo)
  }

  render() {
    if (this.state.hasError && this.state.error) {
      return (
        <div className="chart-container" style={{ textAlign: 'center', padding: '3rem 2rem', maxWidth: 520, margin: '2rem auto' }}>
          <h2 style={{ margin: '0 0 1rem', color: 'var(--text)' }}>Something went wrong</h2>
          <p style={{ color: 'var(--text-muted)', marginBottom: '1rem', fontSize: '0.95rem' }}>
            {getErrorMessage(this.state.error)}
          </p>
          <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem', fontSize: '0.875rem' }}>
            Try refreshing the page or navigating elsewhere.
          </p>
          <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center', flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn"
              onClick={() => this.setState({ hasError: false, error: null })}
            >
              Try again
            </button>
            <Link to="/" className="btn" style={{ textDecoration: 'none' }}>
              Go to Dashboard
            </Link>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
