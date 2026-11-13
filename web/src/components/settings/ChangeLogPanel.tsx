import { useCallback, useEffect, useState } from 'react'
import { getChangeLog } from '../../api'
import type { ChangeLogEntry } from '../../api'

/** "link:event_edit:Store organiser" -> "Edit link · Store organiser"; "admin" -> "Admin". */
const LINK_TYPE_LABELS: Record<string, string> = {
  event_edit: 'Edit link',
  deck_upload: 'Upload link',
  deck_update: 'Deck update link',
  feedback: 'Feedback link',
}

export function describeActor(actor: string): string {
  if (actor === 'admin') return 'Admin'
  if (!actor.startsWith('link:')) return actor || 'Unknown'
  const [, type = '', ...label] = actor.split(':')
  const name = label.join(':')
  const kind = LINK_TYPE_LABELS[type] ?? 'Link'
  return name && name !== 'unlabelled' ? `${kind} · ${name}` : kind
}

function when(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return isNaN(d.getTime()) ? '—' : d.toLocaleString()
}

/** Newest-first list of recorded data changes: when, who, what. */
export default function ChangeLogPanel() {
  const [changes, setChanges] = useState<ChangeLogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [eventFilter, setEventFilter] = useState('')

  const load = useCallback((eventId: string) => {
    setLoading(true)
    setError(null)
    return getChangeLog(eventId.trim() || undefined)
      .then((res) => setChanges(res.changes))
      .catch((e) => setError(e instanceof Error ? e.message : 'Could not load the change log.'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load('')
  }, [load])

  return (
    <div className="chart-container" style={{ maxWidth: 800, marginBottom: '2rem' }}>
      <h2 style={{ margin: '0 0 1rem', fontSize: '1.25rem' }}>Change log</h2>
      <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '1rem' }}>
        Every change to events, decks, matchups, players and settings from the last 180 days: when it happened and
        whether it came from you or through a link.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          load(eventFilter)
        }}
        style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '1rem', alignItems: 'end' }}
      >
        <div className="form-group" style={{ margin: 0 }}>
          <label htmlFor="change-log-event">Event ID</label>
          <input
            id="change-log-event"
            type="text"
            value={eventFilter}
            onChange={(e) => setEventFilter(e.target.value)}
            placeholder="All events"
          />
        </div>
        <button type="submit" className="btn" style={{ padding: '0.35rem 0.75rem' }} disabled={loading}>
          {loading ? 'Loading...' : 'Show'}
        </button>
      </form>

      {error && (
        <p role="alert" style={{ color: 'var(--danger, #dc3545)', marginBottom: '1rem' }}>
          {error}
        </p>
      )}

      {!loading && !error && changes.length === 0 ? (
        <p style={{ color: 'var(--text-muted)' }}>No changes recorded{eventFilter.trim() ? ' for this event' : ' yet'}.</p>
      ) : (
        changes.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Who</th>
                  <th>What</th>
                  <th>Event</th>
                </tr>
              </thead>
              <tbody>
                {changes.map((c) => (
                  <tr key={c.id}>
                    <td style={{ whiteSpace: 'nowrap' }}>{when(c.at)}</td>
                    <td>{describeActor(c.actor)}</td>
                    <td>{c.summary}</td>
                    <td>{c.event_id ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  )
}
