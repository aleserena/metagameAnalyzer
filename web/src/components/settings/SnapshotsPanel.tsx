import { useCallback, useEffect, useState } from 'react'
import { getSnapshots, restoreSnapshot } from '../../api'
import type { EventSnapshot } from '../../api'

/** Why a snapshot was taken, in the words an admin would use. */
const REASON_LABELS: Record<string, string> = {
  delete: 'Before delete',
  merge: 'Before merge',
  hadouken: 'Before Hadouken import',
  clear_decks: 'Before clearing all decks',
  rescrape: 'Before re-scrape',
  before_restore: 'Before a restore',
  renumber_rounds: 'Before renumbering bracket rounds',
}

function when(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return isNaN(d.getTime()) ? '—' : d.toLocaleString()
}

/**
 * Event snapshots: how an event looked before something destructive happened to it, with a
 * one-click restore. See docs/BACKUP_RESTORE.md.
 */
export default function SnapshotsPanel() {
  const [snapshots, setSnapshots] = useState<EventSnapshot[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [pending, setPending] = useState<EventSnapshot | null>(null)
  const [restoring, setRestoring] = useState(false)

  const [search, setSearch] = useState('')

  const load = useCallback((term: string) => {
    return getSnapshots(term.trim() || undefined)
      .then((res) => setSnapshots(res.snapshots))
      .catch((e) => setError(e instanceof Error ? e.message : 'Could not load snapshots.'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load('')
  }, [load])

  const confirmRestore = async () => {
    if (!pending) return
    setRestoring(true)
    setError(null)
    setNotice(null)
    try {
      const result = await restoreSnapshot(pending.id)
      const others = result.also_saved_event_ids ?? []
      setNotice(
        others.length > 0
          ? `Event restored. Its decks were taken back from event ${others.join(', ')}, which was saved first.`
          : 'Event restored.'
      )
      await load(search)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not restore the event.')
    } finally {
      setRestoring(false)
      setPending(null)
    }
  }

  return (
    <div className="chart-container" style={{ maxWidth: 800, marginBottom: '2rem' }}>
      <h2 style={{ margin: '0 0 1rem', fontSize: '1.25rem' }}>Event snapshots</h2>
      <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '1rem' }}>
        A copy of an event is saved automatically before it is deleted, merged, changed by a Hadouken import or a
        re-scrape, or before all decks are cleared. Restoring puts the event back exactly as it was: decks, matchups
        and player emails.
      </p>

      {error && (
        <p role="alert" style={{ color: 'var(--danger, #dc3545)', marginBottom: '1rem' }}>
          {error}
        </p>
      )}
      {notice && (
        <p role="status" style={{ color: 'var(--text)', marginBottom: '1rem' }}>
          {notice}
        </p>
      )}

      {pending && (
        <div
          role="alertdialog"
          aria-label="Confirm restore"
          style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '1rem', marginBottom: '1rem' }}
        >
          <p style={{ margin: '0 0 0.75rem' }}>
            Restore &quot;{pending.event_name || pending.event_id}&quot; to how it was on {when(pending.created_at)}?
            The current version is saved first, so this can be undone.
          </p>
          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
            <button type="button" className="btn" onClick={confirmRestore} disabled={restoring}>
              {restoring ? 'Restoring...' : 'Restore event'}
            </button>
            <button type="button" className="btn" onClick={() => setPending(null)} disabled={restoring}>
              Cancel
            </button>
          </div>
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault()
          setLoading(true)
          load(search)
        }}
        style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '1rem', alignItems: 'end' }}
      >
        <div className="form-group" style={{ margin: 0 }}>
          <label htmlFor="snapshot-search">Event name or ID</label>
          <input
            id="snapshot-search"
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Newest 200 snapshots"
          />
        </div>
        <button type="submit" className="btn" style={{ padding: '0.35rem 0.75rem' }} disabled={loading}>
          Search
        </button>
      </form>

      {loading ? (
        <p style={{ color: 'var(--text-muted)' }}>Loading...</p>
      ) : snapshots.length === 0 ? (
        <p style={{ color: 'var(--text-muted)' }}>
          {search.trim()
            ? 'No snapshots match that event.'
            : 'No snapshots yet. One is saved the next time an event is deleted, merged, imported over or re-scraped.'}
        </p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Event</th>
                <th>Saved</th>
                <th>Why</th>
                <th>Decks</th>
                <th>Matchups</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {snapshots.map((s) => (
                <tr key={s.id}>
                  <td>{s.event_name || s.event_id}</td>
                  <td>{when(s.created_at)}</td>
                  <td>{REASON_LABELS[s.reason] ?? s.reason}</td>
                  <td>{s.deck_count}</td>
                  <td>{s.matchup_count}</td>
                  <td>
                    <button
                      type="button"
                      className="btn"
                      style={{ padding: '0.25rem 0.6rem' }}
                      onClick={() => {
                        setNotice(null)
                        setError(null)
                        setPending(s)
                      }}
                      disabled={restoring}
                    >
                      Restore
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
