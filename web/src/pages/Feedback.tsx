import { useState } from 'react'
import toast from 'react-hot-toast'
import { submitFeedback } from '../api'
import { GITHUB_REPO } from '../config'
import { reportError } from '../utils'

const ISSUE_TYPES = [
  { label: 'Bug report', value: 'bug' },
  { label: 'Feature request', value: 'enhancement' },
  { label: 'Other', value: 'question' },
] as const

export default function Feedback() {
  const [type, setType] = useState<string>(ISSUE_TYPES[0].value)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [email, setEmail] = useState('')
  const [website, setWebsite] = useState('') // honeypot: leave empty; bots often fill it
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const t = (title || '').trim()
    const d = (description || '').trim()
    if (!t || !d) {
      toast.error('Title and description are required')
      return
    }
    setSubmitting(true)
    try {
      const result = await submitFeedback({
        type,
        title: t,
        description: d,
        email: (email || '').trim() || undefined,
        website: (website || '').trim() || undefined,
      })
      toast.success(
        result.url ? (
          <span>
            Issue created.{' '}
            <a href={result.url} target="_blank" rel="noopener noreferrer" style={{ color: 'inherit', textDecoration: 'underline' }}>
              View on GitHub
            </a>
          </span>
        ) : (
          'Issue created.'
        )
      )
      setTitle('')
      setDescription('')
      setEmail('')
      setWebsite('')
    } catch (e) {
      toast.error(reportError(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="chart-container" style={{ maxWidth: 520, margin: '2rem auto' }}>
      <h1 className="page-title">Feedback</h1>
      <p style={{ marginBottom: '1.5rem', color: 'var(--text-muted, #666)' }}>
        Report a bug or suggest a feature. No GitHub account needed—we create the issue for you.{' '}
        If you have a GitHub account, you can{' '}
        <a href={`${GITHUB_REPO}/issues/new`} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--link-color, #0066cc)', textDecoration: 'underline' }}>
          open an issue on GitHub
        </a>
        .
      </p>
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="feedback-type">Issue type</label>
          <select
            id="feedback-type"
            value={type}
            onChange={(e) => setType(e.target.value)}
            disabled={submitting}
          >
            {ISSUE_TYPES.map(({ label, value }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label htmlFor="feedback-title">Title</label>
          <input
            id="feedback-title"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Short summary"
            maxLength={256}
            disabled={submitting}
            required
          />
        </div>
        <div className="form-group">
          <label htmlFor="feedback-description">Description</label>
          <textarea
            id="feedback-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe the bug or feature in detail..."
            rows={5}
            disabled={submitting}
            required
          />
        </div>
        <div className="form-group">
          <label htmlFor="feedback-email">Email (optional)</label>
          <input
            id="feedback-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="So we can follow up if needed"
            disabled={submitting}
          />
        </div>
        {/* Honeypot: hidden from users, off-screen and out of tab order; bots often fill it */}
        <div
          style={{ position: 'absolute', left: '-9999px', width: '1px', height: '1px', overflow: 'hidden' }}
          aria-hidden="true"
        >
          <label htmlFor="feedback-website">Website</label>
          <input
            id="feedback-website"
            type="text"
            name="website"
            value={website}
            onChange={(e) => setWebsite(e.target.value)}
            tabIndex={-1}
            autoComplete="off"
            disabled={submitting}
          />
        </div>
        <button type="submit" className="btn" disabled={submitting}>
          {submitting ? 'Submitting...' : 'Submit feedback'}
        </button>
      </form>
    </div>
  )
}
