import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { getEvent, getDecks, updateEvent, addDeckToEvent, deleteEvent, createEventUploadLinks } from '../api'
import type { EventWithOrigin } from '../api'
import type { Deck } from '../types'
import { useAuth } from '../contexts/AuthContext'
import { reportError, ddMmYyToIso, isoToDdMmYy } from '../utils'

/** Coerce value for display; avoid [object Object]. */
function cellStr(v: unknown): string {
  if (v == null) return '—'
  if (typeof v === 'object') return '—'
  return String(v)
}

export default function EventDetail() {
  const { eventId } = useParams<{ eventId: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const [event, setEvent] = useState<(EventWithOrigin & { player_count?: number }) | null>(null)
  const [decks, setDecks] = useState<Deck[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState('')
  const [editStore, setEditStore] = useState('')
  const [editLocation, setEditLocation] = useState('')
  const [editDate, setEditDate] = useState('')
  const [editFormatId, setEditFormatId] = useState('')
  const [editPlayerCount, setEditPlayerCount] = useState(0)
  const [saving, setSaving] = useState(false)
  const [addingDeck, setAddingDeck] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [generatingLinks, setGeneratingLinks] = useState(false)
  const [generatedLinks, setGeneratedLinks] = useState<Array<{ token: string; url: string; expires_at: string | null }>>([])

  useEffect(() => {
    if (!eventId) return
    setLoading(true)
    setError(null)
    Promise.all([getEvent(eventId), getDecks({ event_id: eventId, limit: 500 })])
      .then(([ev, decksRes]) => {
        setEvent(ev)
        setEditName(ev.event_name || '')
        setEditStore(ev.store ?? '')
        setEditLocation(ev.location ?? '')
        setEditDate(ev.date || '')
        setEditFormatId(ev.format_id || '')
        setEditPlayerCount(ev.player_count ?? 0)
        setDecks(decksRes.decks)
      })
      .catch((e) => {
        setError(e.message)
        toast.error(reportError(e))
      })
      .finally(() => setLoading(false))
  }, [eventId])

  const startEdit = () => {
    if (event) {
      setEditName(event.event_name || '')
      setEditStore(event.store ?? '')
      setEditLocation(event.location ?? '')
      setEditDate(event.date || '')
      setEditFormatId(event.format_id || '')
      setEditPlayerCount(event.player_count ?? 0)
      setEditing(true)
    }
  }

  const cancelEdit = () => setEditing(false)

  const saveEdit = () => {
    if (!eventId) return
    setSaving(true)
    updateEvent(eventId, {
      event_name: editName,
      date: editDate,
      format_id: editFormatId,
      player_count: editPlayerCount,
      store: editStore,
      location: editLocation,
    })
      .then(() => {
        setEvent((prev) =>
          prev
            ? { ...prev, event_name: editName, store: editStore, location: editLocation, date: editDate, format_id: editFormatId, player_count: editPlayerCount }
            : null
        )
        setEditing(false)
        toast.success('Event updated')
      })
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setSaving(false))
  }

  const handleAddDeck = () => {
    if (!eventId) return
    setAddingDeck(true)
    addDeckToEvent(eventId)
      .then((r) => {
        toast.success(r.message)
        return getDecks({ event_id: eventId, limit: 500 })
      })
      .then((res) => setDecks(res.decks))
      .catch((err) => toast.error(reportError(err)))
      .finally(() => setAddingDeck(false))
  }

  const handleDelete = () => {
    if (!eventId || !window.confirm('Delete this event and all its decks?')) return
    setDeleting(true)
    deleteEvent(eventId)
      .then(() => {
        toast.success('Event deleted')
        navigate('/events')
      })
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setDeleting(false))
  }

  const handleGenerateUploadLink = () => {
    if (!eventId) return
    setGeneratingLinks(true)
    createEventUploadLinks(eventId, { count: 1 })
      .then((res) => {
        const base = typeof window !== 'undefined' ? window.location.origin : ''
        const linksWithUrls = res.links.map((l) => ({ ...l, url: `${base}/upload/${l.token}` }))
        setGeneratedLinks((prev) => [...linksWithUrls, ...prev])
        if (linksWithUrls.length > 0) {
          const url = linksWithUrls[0].url
          window.navigator.clipboard.writeText(url).then(
            () => toast.success('Link copied to clipboard'),
            () => toast.success('Upload link generated')
          )
        }
      })
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setGeneratingLinks(false))
  }

  const copyLink = (url: string) => {
    window.navigator.clipboard.writeText(url).then(
      () => toast.success('Copied to clipboard'),
      () => { /* ignore */ }
    )
  }

  if (loading) return <div className="page"><p>Loading…</p></div>
  if (error || !event) {
    return (
      <div className="page">
        <h1 className="page-title">Event</h1>
        <p style={{ color: 'var(--text-muted)' }}>{error || 'Event not found.'}</p>
        <Link to="/events" className="btn">Back to events</Link>
      </div>
    )
  }

  return (
    <div className="page">
      <button type="button" className="btn" style={{ marginBottom: '1rem' }} onClick={() => navigate(-1)}>
        Back
      </button>
      <h1 className="page-title">
        {[event.event_name, event.store, event.location].filter(Boolean).length >= 2
          ? `${event.event_name || 'Unnamed'}${event.store ? ` @ ${event.store}` : ''}${event.location ? ` (${event.location})` : ''}`
          : (typeof event.event_name === 'string' && event.event_name.trim()) ? event.event_name : 'Unnamed event'}
      </h1>

      <section className="card" style={{ marginBottom: '1.5rem' }}>
        {editing ? (
          <>
            <h2 style={{ marginTop: 0 }}>Edit event</h2>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', marginBottom: '1rem' }}>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="label">Name</span>
                <input type="text" value={editName} onChange={(e) => setEditName(e.target.value)} style={{ minWidth: 240 }} />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="label">Store</span>
                <input type="text" value={editStore} onChange={(e) => setEditStore(e.target.value)} style={{ minWidth: 120 }} />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="label">Location</span>
                <input type="text" value={editLocation} onChange={(e) => setEditLocation(e.target.value)} style={{ minWidth: 120 }} />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="label">Date</span>
                <input
                  type="date"
                  value={ddMmYyToIso(editDate)}
                  onChange={(e) => setEditDate(isoToDdMmYy(e.target.value))}
                  style={{ width: 140 }}
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="label">Format</span>
                <input type="text" value={editFormatId} onChange={(e) => setEditFormatId(e.target.value)} style={{ width: 80 }} />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="label">Players</span>
                <input
                  type="number"
                  min={0}
                  value={editPlayerCount || ''}
                  onChange={(e) => setEditPlayerCount(parseInt(e.target.value, 10) || 0)}
                  style={{ width: 70 }}
                />
              </label>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button type="button" className="btn btn-primary" onClick={saveEdit} disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
              <button type="button" className="btn" onClick={cancelEdit}>Cancel</button>
            </div>
          </>
        ) : (
          <>
            <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '0.5rem 1.5rem', margin: 0 }}>
              <dt style={{ color: 'var(--text-muted)' }}>Date</dt>
              <dd style={{ margin: 0 }}>{cellStr(event.date)}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Format</dt>
              <dd style={{ margin: 0 }}>{cellStr(event.format_id)}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Players</dt>
              <dd style={{ margin: 0 }}>{typeof event.player_count === 'number' ? event.player_count : cellStr(event.player_count)}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Store</dt>
              <dd style={{ margin: 0 }}>{cellStr(event.store) || '—'}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Location</dt>
              <dd style={{ margin: 0 }}>{cellStr(event.location) || '—'}</dd>
            </dl>
            {user === 'admin' && (
              <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <button type="button" className="btn" onClick={startEdit}>Edit event</button>
                <button type="button" className="btn" onClick={handleAddDeck} disabled={addingDeck}>
                  {addingDeck ? 'Adding…' : 'Add deck'}
                </button>
                <button type="button" className="btn" style={{ color: 'var(--danger, #c00)' }} onClick={handleDelete} disabled={deleting}>
                  Delete event
                </button>
              </div>
            )}
          </>
        )}
      </section>

      {user === 'admin' && (
        <section className="card" style={{ marginBottom: '1.5rem' }}>
          <h2 style={{ marginTop: 0 }}>Upload links</h2>
          <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>
            Generate a one-time link so a player can upload their deck to this event. Each link can be used only once.
          </p>
          <button
            type="button"
            className="btn"
            onClick={handleGenerateUploadLink}
            disabled={generatingLinks}
          >
            {generatingLinks ? 'Generating…' : 'Generate upload link'}
          </button>
          {generatedLinks.length > 0 && (
            <ul style={{ marginTop: '1rem', paddingLeft: '1.25rem' }}>
              {generatedLinks.map((link) => (
                <li key={link.token} style={{ marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <code style={{ fontSize: '0.875rem', wordBreak: 'break-all' }}>{link.url}</code>
                  <button type="button" className="btn" style={{ flexShrink: 0 }} onClick={() => copyLink(link.url)}>
                    Copy
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <h2>Decks ({decks.length})</h2>
      {decks.length === 0 ? (
        <p style={{ color: 'var(--text-muted)' }}>No decks in this event yet. {user === 'admin' && 'Click "Add deck" above to add one.'}</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Deck</th>
                <th scope="col">Player</th>
                <th scope="col">Rank</th>
                <th scope="col">Archetype</th>
              </tr>
            </thead>
            <tbody>
              {decks.map((d) => (
                <tr key={d.deck_id}>
                  <td>
                    <Link to={`/decks/${d.deck_id}`} style={{ color: 'var(--accent)' }}>{cellStr(d.name) || 'Unnamed'}</Link>
                  </td>
                  <td>{cellStr(d.player)}</td>
                  <td>{cellStr(d.rank) || '—'}</td>
                  <td>{cellStr(d.archetype)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
