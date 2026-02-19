import { useEffect, useState, useRef } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { getDecks, getEvents, getDateRange, getDuplicateDecks } from '../api'
import type { Deck, Event } from '../types'
import EventSelector from '../components/EventSelector'
import { Skeleton, SkeletonTable } from '../components/Skeleton'

const DEBOUNCE_MS = 300

export default function Decks() {
  const [decks, setDecks] = useState<Deck[]>([])
  const [events, setEvents] = useState<Event[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const eventIdsParam = searchParams.get('event_ids') ?? searchParams.get('event_id')
  const eventIds = eventIdsParam
    ? eventIdsParam.split(',').map((s) => parseInt(s.trim(), 10)).filter((n) => !isNaN(n))
    : []
  const [maxDate, setMaxDate] = useState<string | null>(null)
  const [lastEventDate, setLastEventDate] = useState<string | null>(null)
  const [duplicateDeckIds, setDuplicateDeckIds] = useState<Set<number>>(new Set())
  const deckName = searchParams.get('deck_name')
  const archetype = searchParams.get('archetype')
  const player = searchParams.get('player')
  const card = searchParams.get('card')
  const sort = searchParams.get('sort') ?? 'date'
  const order = searchParams.get('order') ?? 'desc'
  const page = parseInt(searchParams.get('page') ?? '1', 10)
  const limit = 25
  const skip = (page - 1) * limit

  const [localDeckName, setLocalDeckName] = useState(deckName ?? '')
  const [localArchetype, setLocalArchetype] = useState(archetype ?? '')
  const [localPlayer, setLocalPlayer] = useState(player ?? '')
  const [localCard, setLocalCard] = useState(card ?? '')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const setEventIdsFilter = (ids: number[]) => {
    setFilter('event_ids', ids.length ? ids.join(',') : null)
  }

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else if (next.size < 4) next.add(id)
      return next
    })
  }

  useEffect(() => {
    setLocalDeckName(deckName ?? '')
    setLocalArchetype(archetype ?? '')
    setLocalPlayer(player ?? '')
    setLocalCard(card ?? '')
  }, [deckName, archetype, player, card])

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      debounceRef.current = null
      const params = new URLSearchParams(searchParams)
      if (localDeckName) params.set('deck_name', localDeckName)
      else params.delete('deck_name')
      if (localArchetype) params.set('archetype', localArchetype)
      else params.delete('archetype')
      if (localPlayer) params.set('player', localPlayer)
      else params.delete('player')
      if (localCard) params.set('card', localCard)
      else params.delete('card')
      params.delete('page')
      const next = params.toString()
      if (next !== searchParams.toString()) navigate({ search: next })
    }, DEBOUNCE_MS)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [localDeckName, localArchetype, localPlayer, localCard])

  useEffect(() => {
    getEvents().then((r) => setEvents(r.events))
    getDateRange().then((r) => {
      setMaxDate(r.max_date)
      setLastEventDate(r.last_event_date)
    })
  }, [])

  useEffect(() => {
    getDuplicateDecks(eventIds.length ? eventIds.join(',') : undefined)
      .then((r) => {
        const ids = new Set<number>()
        for (const g of r.duplicates) {
          ids.add(g.primary_deck_id)
          g.duplicate_deck_ids.forEach((id) => ids.add(id))
        }
        setDuplicateDeckIds(ids)
      })
      .catch(() => setDuplicateDeckIds(new Set()))
  }, [eventIdsParam])

  useEffect(() => {
    setLoading(true)
    getDecks({
      event_ids: eventIds.length ? eventIds.join(',') : undefined,
      deck_name: deckName ?? undefined,
      archetype: archetype ?? undefined,
      player: player ?? undefined,
      card: card ?? undefined,
      sort,
      order,
      skip,
      limit,
    })
      .then((r) => {
        setDecks(r.decks)
        setTotal(r.total)
      })
      .catch((e) => {
        setError(e.message)
        toast.error(e.message)
      })
      .finally(() => setLoading(false))
  }, [eventIdsParam, deckName, archetype, player, card, sort, order, skip, limit])

  const setFilter = (key: string, value: string | null) => {
    const params = new URLSearchParams(searchParams)
    if (value) params.set(key, value)
    else params.delete(key)
    params.delete('page')
    navigate({ search: params.toString() })
  }

  const handleSortHeader = (sortKey: 'date' | 'rank' | 'name' | 'player') => {
    const nextOrder = sort === sortKey ? (order === 'asc' ? 'desc' : 'asc') : sortKey === 'date' || sortKey === 'rank' ? 'desc' : 'asc'
    const params = new URLSearchParams(searchParams)
    params.set('sort', sortKey)
    params.set('order', nextOrder)
    params.delete('page')
    navigate({ search: params.toString() })
  }

  const clearFilters = () => {
    setLocalDeckName('')
    setLocalArchetype('')
    setLocalPlayer('')
    setLocalCard('')
    navigate({ pathname: '/decks', search: '' })
  }

  const retryLoad = () => {
    setError(null)
    setLoading(true)
    getDecks({
      event_ids: eventIds.length ? eventIds.join(',') : undefined,
      deck_name: deckName ?? undefined,
      archetype: archetype ?? undefined,
      player: player ?? undefined,
      card: card ?? undefined,
      sort,
      order,
      skip,
      limit,
    })
      .then((r) => {
        setDecks(r.decks)
        setTotal(r.total)
      })
      .catch((e) => {
        setError(e.message)
        toast.error(e.message)
      })
      .finally(() => setLoading(false))
  }

  const hasActiveFilters = !!(eventIds.length || deckName || archetype || player || card)
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

      <div style={{ display: 'flex', gap: '1.5rem', marginBottom: '1.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div
          className="filters-group"
          style={{
            display: 'flex',
            gap: '1rem',
            flexWrap: 'wrap',
            alignItems: 'flex-end',
            padding: '1rem',
            background: 'var(--bg)',
            border: '1px solid var(--border)',
            borderRadius: 8,
          }}
        >
          <span style={{ width: '100%', fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Filters
          </span>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label htmlFor="decks-name">Deck name</label>
            <input
              id="decks-name"
              type="text"
              placeholder="Search deck name..."
              value={localDeckName}
              onChange={(e) => setLocalDeckName(e.target.value)}
              aria-label="Search deck name"
            />
          </div>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label htmlFor="decks-archetype">Archetype</label>
            <input
              id="decks-archetype"
              type="text"
              placeholder="Search archetype..."
              value={localArchetype}
              onChange={(e) => setLocalArchetype(e.target.value)}
              aria-label="Search archetype"
            />
          </div>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label htmlFor="decks-player">Player</label>
            <input
              id="decks-player"
              type="text"
              placeholder="Search player..."
              value={localPlayer}
              onChange={(e) => setLocalPlayer(e.target.value)}
              aria-label="Search player"
            />
          </div>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label htmlFor="decks-card">Card</label>
            <input
              id="decks-card"
              type="text"
              placeholder="Search by card..."
              value={localCard}
              onChange={(e) => setLocalCard(e.target.value)}
              aria-label="Search by card"
            />
          </div>
          <EventSelector
            events={events}
            selectedIds={eventIds}
            onChange={setEventIdsFilter}
            showDatePresets
            maxDate={maxDate}
            lastEventDate={lastEventDate}
          />
          {hasActiveFilters && (
            <button type="button" className="btn" onClick={clearFilters} style={{ marginBottom: 0 }}>
              Clear filters
            </button>
          )}
        </div>
      </div>

      {error && !loading ? (
        <div className="chart-container" style={{ textAlign: 'center', padding: '2rem' }}>
          <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>{error}</p>
          <button type="button" className="btn" onClick={retryLoad}>
            Try again
          </button>
        </div>
      ) : loading ? (
        <>
          <Skeleton width={120} height={16} style={{ marginBottom: '0.5rem' }} />
          <SkeletonTable rows={10} />
        </>
      ) : total === 0 ? (
        <div className="chart-container" style={{ textAlign: 'center', padding: '3rem 2rem' }}>
          <p style={{ color: 'var(--text-muted)', marginBottom: '1rem', fontSize: '1.1rem' }}>
            No decks found
          </p>
          <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
            {hasActiveFilters
              ? 'Try adjusting your filters or clear them to see all decks.'
              : 'Load or scrape data first to browse decks.'}
          </p>
          <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center', flexWrap: 'wrap' }}>
            {hasActiveFilters ? (
              <button type="button" className="btn" onClick={clearFilters}>
                Clear filters
              </button>
            ) : (
              <Link to="/scrape" className="btn" style={{ textDecoration: 'none' }}>
                Load or scrape data
              </Link>
            )}
          </div>
        </div>
      ) : (
        <>
          <div style={{ marginBottom: '0.5rem', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
            {total} {total === 1 ? 'deck' : 'decks'} found
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col" style={{ width: 32 }} aria-label="Select for comparison"></th>
                  <th
                    scope="col"
                    className="sortable"
                    style={{ cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSortHeader('name')}
                    title="Sort by deck name"
                    aria-sort={sort === 'name' ? (order === 'asc' ? 'ascending' : 'descending') : undefined}
                  >
                    Deck {sort === 'name' && (order === 'asc' ? '↑' : '↓')}
                  </th>
                  <th
                    scope="col"
                    className="sortable"
                    style={{ cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSortHeader('player')}
                    title="Sort by player"
                    aria-sort={sort === 'player' ? (order === 'asc' ? 'ascending' : 'descending') : undefined}
                  >
                    Player {sort === 'player' && (order === 'asc' ? '↑' : '↓')}
                  </th>
                  <th scope="col">Event</th>
                  <th
                    scope="col"
                    className="sortable"
                    style={{ cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSortHeader('date')}
                    title="Sort by date"
                    aria-sort={sort === 'date' ? (order === 'asc' ? 'ascending' : 'descending') : undefined}
                  >
                    Date {sort === 'date' && (order === 'asc' ? '↑' : '↓')}
                  </th>
                  <th
                    scope="col"
                    className="sortable"
                    style={{ cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSortHeader('rank')}
                    title="Sort by rank"
                    aria-sort={sort === 'rank' ? (order === 'asc' ? 'ascending' : 'descending') : undefined}
                  >
                    Rank {sort === 'rank' && (order === 'asc' ? '↑' : '↓')}
                  </th>
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
                      {duplicateDeckIds.has(d.deck_id) && (
                        <span
                          style={{
                            marginLeft: 6,
                            fontSize: '0.7rem',
                            padding: '0.1rem 0.35rem',
                            background: 'rgba(247, 147, 26, 0.2)',
                            borderRadius: 4,
                            color: 'var(--warning)',
                          }}
                          title="Identical mainboard to another deck"
                        >
                          dup
                        </span>
                      )}
                    </td>
                    <td
                      style={{ cursor: 'pointer', color: 'var(--accent)' }}
                      onClick={(e) => { e.stopPropagation(); navigate(`/players/${encodeURIComponent(d.player)}`) }}
                    >
                      {d.player}
                    </td>
                    <td
                      style={{ cursor: 'pointer', color: 'var(--accent)' }}
                      onClick={(e) => { e.stopPropagation(); navigate(`/decks?event_ids=${d.event_id}`) }}
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
