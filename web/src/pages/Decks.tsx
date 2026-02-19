import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { getDecks, getEvents } from '../api'
import type { Deck, Event } from '../types'

export default function Decks() {
  const [decks, setDecks] = useState<Deck[]>([])
  const [events, setEvents] = useState<Event[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else if (next.size < 4) next.add(id)
      return next
    })
  }

  const eventId = searchParams.get('event_id')
  const deckName = searchParams.get('deck_name')
  const player = searchParams.get('player')
  const card = searchParams.get('card')
  const page = parseInt(searchParams.get('page') ?? '1', 10)
  const limit = 25
  const skip = (page - 1) * limit

  useEffect(() => {
    getEvents().then((r) => setEvents(r.events))
  }, [])

  useEffect(() => {
    setLoading(true)
    getDecks({
      event_id: eventId ? parseInt(eventId, 10) : undefined,
      deck_name: deckName ?? undefined,
      player: player ?? undefined,
      card: card ?? undefined,
      skip,
      limit,
    })
      .then((r) => {
        setDecks(r.decks)
        setTotal(r.total)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [eventId, deckName, player, card, skip, limit])

  const setFilter = (key: string, value: string | null) => {
    const params = new URLSearchParams(searchParams)
    if (value) params.set(key, value)
    else params.delete(key)
    params.delete('page')
    navigate({ search: params.toString() })
  }

  if (error) return <div className="error">{error}</div>

  const totalPages = Math.ceil(total / limit)

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem', flexWrap: 'wrap', gap: '0.5rem' }}>
        <h1 className="page-title" style={{ margin: 0 }}>Decks</h1>
        {selected.size >= 2 && (
          <button
            className="btn"
            onClick={() => navigate(`/decks/compare?ids=${[...selected].join(',')}`)}
          >
            Compare {selected.size} decks
          </button>
        )}
        {selected.size > 0 && selected.size < 2 && (
          <span style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
            Select at least 2 decks to compare ({selected.size}/4)
          </span>
        )}
      </div>

      <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label>Deck name</label>
          <input
            type="text"
            placeholder="Search deck name..."
            value={deckName ?? ''}
            onChange={(e) => setFilter('deck_name', e.target.value || null)}
          />
        </div>
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label>Player</label>
          <input
            type="text"
            placeholder="Search player..."
            value={player ?? ''}
            onChange={(e) => setFilter('player', e.target.value || null)}
          />
        </div>
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label>Card</label>
          <input
            type="text"
            placeholder="Search by card..."
            value={card ?? ''}
            onChange={(e) => setFilter('card', e.target.value || null)}
          />
        </div>
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label>Event</label>
          <select
            value={eventId ?? ''}
            onChange={(e) => setFilter('event_id', e.target.value || null)}
          >
            <option value="">All events</option>
            {events.map((e) => (
              <option key={e.event_id} value={e.event_id}>
                {e.event_name} ({e.date})
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <div className="loading">Loading...</div>
      ) : (
        <>
          <div style={{ marginBottom: '0.5rem', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
            {total} {total === 1 ? 'deck' : 'decks'} found
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 32 }}></th>
                  <th>Deck</th>
                  <th>Player</th>
                  <th>Event</th>
                  <th>Date</th>
                  <th>Rank</th>
                </tr>
              </thead>
              <tbody>
                {decks.map((d) => (
                  <tr
                    key={d.deck_id}
                    className="clickable"
                    onClick={() => navigate(`/decks/${d.deck_id}`)}
                  >
                    <td onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selected.has(d.deck_id)}
                        onChange={() => toggleSelect(d.deck_id)}
                        title="Select for comparison"
                      />
                    </td>
                    <td
                      style={{ cursor: 'pointer', color: 'var(--accent)' }}
                      onClick={(e) => { e.stopPropagation(); navigate(`/decks/${d.deck_id}`) }}
                    >
                      {d.name}
                    </td>
                    <td
                      style={{ cursor: 'pointer', color: 'var(--accent)' }}
                      onClick={(e) => { e.stopPropagation(); navigate(`/players/${encodeURIComponent(d.player)}`) }}
                    >
                      {d.player}
                    </td>
                    <td
                      style={{ cursor: 'pointer', color: 'var(--accent)' }}
                      onClick={(e) => { e.stopPropagation(); navigate(`/decks?event_id=${d.event_id}`) }}
                    >
                      {d.event_name}
                    </td>
                    <td>{d.date}</td>
                    <td>{d.rank || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <button
                className="btn"
                disabled={page <= 1}
                onClick={() => {
                  const p = new URLSearchParams(searchParams)
                  p.set('page', String(page - 1))
                  navigate({ search: p.toString() })
                }}
              >
                Previous
              </button>
              <span>
                Page {page} of {totalPages} ({total} decks)
              </span>
              <button
                className="btn"
                disabled={page >= totalPages}
                onClick={() => {
                  const p = new URLSearchParams(searchParams)
                  p.set('page', String(page + 1))
                  navigate({ search: p.toString() })
                }}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
