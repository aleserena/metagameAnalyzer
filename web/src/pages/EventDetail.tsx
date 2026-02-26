import { useState, useEffect } from 'react'
import { useParams, Link, useNavigate, useBlocker } from 'react-router-dom'
import toast from 'react-hot-toast'
import { getEvent, getDecks, updateEvent, addDeckToEvent, deleteEvent, createEventUploadLinks, updateDeck, deleteDeck } from '../api'
import type { EventWithOrigin } from '../api'
import type { Deck } from '../types'
import { useAuth } from '../contexts/AuthContext'
import { useFetch } from '../hooks/useFetch'
import PageError from '../components/PageError'
import PageSkeleton from '../components/PageSkeleton'
import CardSearchInput from '../components/CardSearchInput'
import { reportError, ddMmYyToIso, isoToDdMmYy } from '../utils'

/** Coerce value for display; avoid [object Object]. */
function cellStr(v: unknown): string {
  if (v == null) return '—'
  if (typeof v === 'object') return '—'
  return String(v)
}

type EventDetailData = { event: EventWithOrigin & { player_count?: number }; decks: Deck[] }

export default function EventDetail() {
  const { eventId } = useParams<{ eventId: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const { data, loading, error, refetch } = useFetch<EventDetailData>(
    () =>
      eventId
        ? Promise.all([getEvent(eventId), getDecks({ event_id: eventId, limit: 500 })]).then(([ev, decksRes]) => ({
            event: ev,
            decks: decksRes.decks,
          }))
        : Promise.reject(new Error('Missing event ID')),
    [eventId ?? '']
  )
  const event = data?.event ?? null
  const decks = data?.decks ?? []
  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState('')
  const [editStore, setEditStore] = useState('')
  const [editLocation, setEditLocation] = useState('')
  const [editDate, setEditDate] = useState('')
  const [editFormatId, setEditFormatId] = useState('')
  const [editPlayerCount, setEditPlayerCount] = useState(0)
  const [saving, setSaving] = useState(false)
  const [addingDeck, setAddingDeck] = useState(false)
  const [addDecksCount, setAddDecksCount] = useState(1)
  const [addingDecks, setAddingDecks] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [generatingLinks, setGeneratingLinks] = useState(false)
  const [generatedLinks, setGeneratedLinks] = useState<Array<{ token: string; url: string; expires_at: string | null; deck_id?: number }>>([])
  const [generatingUpdateLinkFor, setGeneratingUpdateLinkFor] = useState<number | null>(null)
  const [editingDeckId, setEditingDeckId] = useState<number | null>(null)
  const [editDeckName, setEditDeckName] = useState('')
  const [editDeckPlayer, setEditDeckPlayer] = useState('')
  const [editDeckRank, setEditDeckRank] = useState('')
  const [editDeckArchetype, setEditDeckArchetype] = useState('')
  const [savingDeck, setSavingDeck] = useState(false)
  const [deletingDeckId, setDeletingDeckId] = useState<number | null>(null)

  const isUpdateModalOpen = editingDeckId != null
  useBlocker(isUpdateModalOpen)

  useEffect(() => {
    if (!isUpdateModalOpen) return
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault()
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [isUpdateModalOpen])

  useEffect(() => {
    if (!isUpdateModalOpen) return
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prevOverflow
    }
  }, [isUpdateModalOpen])

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
        refetch()
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
        refetch()
      })
      .catch((err) => toast.error(reportError(err)))
      .finally(() => setAddingDeck(false))
  }

  const handleAddDecks = () => {
    if (!eventId) return
    const count = Math.max(1, Math.min(100, addDecksCount))
    setAddingDecks(true)
    const addOne = (): Promise<unknown> => addDeckToEvent(eventId)
    const chain = Array.from({ length: count }, () => addOne).reduce<Promise<void>>(
      (acc, fn) => acc.then(() => fn()).then(() => undefined),
      Promise.resolve()
    )
    chain
      .then(() => {
        refetch()
        toast.success(`Added ${count} deck${count !== 1 ? 's' : ''}`)
      })
      .catch((e: unknown) => toast.error(reportError(e)))
      .finally(() => setAddingDecks(false))
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

  const handleGenerateUpdateLink = (deckId: number) => {
    if (!eventId) return
    setGeneratingUpdateLinkFor(deckId)
    createEventUploadLinks(eventId, { deck_id: deckId })
      .then((res) => {
        if (res.links.length > 0) {
          const base = typeof window !== 'undefined' ? window.location.origin : ''
          const url = `${base}/upload/${res.links[0].token}`
          window.navigator.clipboard.writeText(url).then(
            () => toast.success('Update link copied to clipboard'),
            () => toast.success('Update link generated')
          )
        }
      })
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setGeneratingUpdateLinkFor(null))
  }

  const openUpdateDeck = (deck: Deck) => {
    setEditingDeckId(deck.deck_id)
    setEditDeckName(deck.name ?? '')
    setEditDeckPlayer(deck.player ?? '')
    setEditDeckRank(deck.rank ?? '')
    setEditDeckArchetype(deck.archetype ?? (deck.commanders?.length ? deck.commanders[0] ?? '' : ''))
  }

  const closeUpdateDeck = () => {
    setEditingDeckId(null)
    setEditDeckName('')
    setEditDeckPlayer('')
    setEditDeckRank('')
    setEditDeckArchetype('')
  }

  const saveDeckUpdate = () => {
    if (editingDeckId == null) return
    const isEDH = (event?.format_id ?? '').toLowerCase() === 'edh' || (event?.format_id ?? '').toLowerCase() === 'commander'
    setSavingDeck(true)
    const payload: Parameters<typeof updateDeck>[1] = {
      name: editDeckName.trim() || undefined,
      player: editDeckPlayer.trim() || undefined,
      rank: editDeckRank.trim() || undefined,
      archetype: editDeckArchetype.trim() || undefined,
    }
    if (isEDH && editDeckArchetype.trim()) {
      payload.commanders = [editDeckArchetype.trim()]
    }
    updateDeck(editingDeckId, payload)
      .then(() => {
        refetch()
        closeUpdateDeck()
        toast.success('Deck updated')
      })
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setSavingDeck(false))
  }

  const handleDeleteDeck = (deckId: number) => {
    if (!window.confirm('Delete this deck? This cannot be undone.')) return
    setDeletingDeckId(deckId)
    deleteDeck(deckId)
      .then(() => {
        refetch()
        toast.success('Deck deleted')
      })
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setDeletingDeckId(null))
  }

  if (loading) return <PageSkeleton titleWidth={280} blocks={2} />
  if (error || !event) {
    return (
      <PageError
        title="Event"
        message={error || 'Event not found.'}
        onRetry={error ? () => refetch() : undefined}
        retryLabel="Try again"
        extraActions={<Link to="/events" className="btn">Back to events</Link>}
      />
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
              <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
                <button type="button" className="btn" onClick={startEdit}>Edit event</button>
                <button type="button" className="btn" onClick={handleAddDeck} disabled={addingDeck || addingDecks}>
                  {addingDeck ? 'Adding…' : 'Add deck'}
                </button>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={addDecksCount}
                    onChange={(ev) => setAddDecksCount(Math.max(1, Math.min(100, parseInt(ev.target.value, 10) || 1)))}
                    style={{ width: 52 }}
                    aria-label="Number of decks to add"
                    disabled={addingDeck || addingDecks}
                  />
                  <button
                    type="button"
                    className="btn"
                    onClick={handleAddDecks}
                    disabled={addingDeck || addingDecks}
                  >
                    {addingDecks ? 'Adding…' : `Add ${addDecksCount} deck${addDecksCount !== 1 ? 's' : ''}`}
                  </button>
                </div>
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
        <div className="table-wrap-outer">
          <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Deck</th>
                <th scope="col">Player</th>
                <th scope="col">Rank</th>
                <th scope="col">Archetype</th>
                {user === 'admin' && <th scope="col">Actions</th>}
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
                  {user === 'admin' && (
                    <td>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', alignItems: 'center' }}>
                        <button
                          type="button"
                          className="btn"
                          style={{ fontSize: '0.875rem', padding: '0.25rem 0.5rem' }}
                          onClick={() => openUpdateDeck(d)}
                        >
                          Update
                        </button>
                        <button
                          type="button"
                          className="btn"
                          style={{ fontSize: '0.875rem', padding: '0.25rem 0.5rem', color: 'var(--danger, #c00)' }}
                          disabled={deletingDeckId === d.deck_id}
                          onClick={() => handleDeleteDeck(d.deck_id)}
                        >
                          {deletingDeckId === d.deck_id ? '…' : 'Delete deck'}
                        </button>
                        <button
                          type="button"
                          className="btn"
                          style={{ fontSize: '0.875rem', padding: '0.25rem 0.5rem' }}
                          disabled={generatingUpdateLinkFor === d.deck_id}
                          onClick={() => handleGenerateUpdateLink(d.deck_id)}
                        >
                          {generatingUpdateLinkFor === d.deck_id ? '…' : 'Update link'}
                        </button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}

      {user === 'admin' && editingDeckId != null && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="update-deck-title"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '1rem',
          }}
          onClick={(e) => e.target === e.currentTarget && closeUpdateDeck()}
        >
          <div
            className="card"
            style={{
              maxWidth: 420,
              width: '100%',
              maxHeight: '90vh',
              overflow: 'auto',
              margin: '1.5rem',
              padding: '1.5rem',
              borderRadius: 12,
              background: 'var(--bg-card)',
              boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="update-deck-title" style={{ marginTop: 0, marginBottom: '1rem' }}>Update deck</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '1rem' }}>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="label">Deck name</span>
                <input
                  type="text"
                  value={editDeckName}
                  onChange={(e) => setEditDeckName(e.target.value)}
                  style={{ width: '100%', boxSizing: 'border-box' }}
                  placeholder="Deck name"
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="label">Player</span>
                <input
                  type="text"
                  value={editDeckPlayer}
                  onChange={(e) => setEditDeckPlayer(e.target.value)}
                  style={{ width: '100%', boxSizing: 'border-box' }}
                  placeholder="Player"
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="label">Rank</span>
                <input
                  type="text"
                  value={editDeckRank}
                  onChange={(e) => setEditDeckRank(e.target.value)}
                  style={{ width: '100%', boxSizing: 'border-box' }}
                  placeholder="e.g. 1, 2, 3-4, 5-8, 9-16, 17-32, 33-64, 65-128"
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="label">
                  {(event?.format_id ?? '').toLowerCase() === 'edh' || (event?.format_id ?? '').toLowerCase() === 'commander'
                    ? 'Archetype (commander)'
                    : 'Archetype'}
                </span>
                {(event?.format_id ?? '').toLowerCase() === 'edh' || (event?.format_id ?? '').toLowerCase() === 'commander' ? (
                  <CardSearchInput
                    value={editDeckArchetype}
                    onChange={setEditDeckArchetype}
                    placeholder="Search commander..."
                    aria-label="Archetype (commander)"
                  />
                ) : (
                  <input
                    type="text"
                    value={editDeckArchetype}
                    onChange={(e) => setEditDeckArchetype(e.target.value)}
                    style={{ width: '100%', boxSizing: 'border-box' }}
                    placeholder="Archetype"
                  />
                )}
              </label>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button type="button" className="btn" onClick={saveDeckUpdate} disabled={savingDeck}>
                {savingDeck ? 'Saving…' : 'Save'}
              </button>
              <button type="button" className="btn" onClick={closeUpdateDeck}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
