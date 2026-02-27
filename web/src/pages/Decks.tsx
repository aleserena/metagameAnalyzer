import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { getDecks, getDuplicateDecks } from '../api'
import type { Deck } from '../types'
import { useEventMetadata } from '../hooks/useEventMetadata'
import { useDebouncedSearchParams } from '../hooks/useDebouncedSearchParams'
import EventSelector from '../components/EventSelector'
import CardSearchInput from '../components/CardSearchInput'
import { Skeleton, SkeletonTable } from '../components/Skeleton'
import ManaSymbols from '../components/ManaSymbols'
import { reportError } from '../utils'

const FILTER_KEYS = ['deck_name', 'archetype', 'player', 'card', 'colors'] as const
const DEBOUNCE_MS = 300

const COLOR_OPTIONS: { value: string; manaCost: string; title: string }[] = [
  { value: 'W', manaCost: '{W}', title: 'White' },
  { value: 'U', manaCost: '{U}', title: 'Blue' },
  { value: 'B', manaCost: '{B}', title: 'Black' },
  { value: 'R', manaCost: '{R}', title: 'Red' },
  { value: 'G', manaCost: '{G}', title: 'Green' },
  { value: 'C', manaCost: '{C}', title: 'Colorless' },
]

export default function Decks() {
  const [decks, setDecks] = useState<Deck[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const { events, maxDate, lastEventDate, error: eventMetadataError } = useEventMetadata()
  const { filters, setFilter } = useDebouncedSearchParams({
    keys: [...FILTER_KEYS],
    debounceMs: DEBOUNCE_MS,
  })
  const eventIdsParam = searchParams.get('event_ids') ?? searchParams.get('event_id')
  const eventIds: (number | string)[] = eventIdsParam
    ? eventIdsParam.split(',').map((s) => s.trim()).filter(Boolean)
    : []
  const [duplicateDeckIds, setDuplicateDeckIds] = useState<Set<number>>(new Set())
  const deckName = searchParams.get('deck_name')
  const archetype = searchParams.get('archetype')
  const player = searchParams.get('player')
  const card = searchParams.get('card')
  const colors = searchParams.get('colors')
  const sort = searchParams.get('sort') ?? 'date'
  const order = searchParams.get('order') ?? 'desc'
  const page = parseInt(searchParams.get('page') ?? '1', 10)
  const limit = 25
  const skip = (page - 1) * limit

  const setUrlParam = (key: string, value: string | null) => {
    const params = new URLSearchParams(searchParams)
    if (value) params.set(key, value)
    else params.delete(key)
    params.delete('page')
    navigate({ search: params.toString() })
  }

  const setEventIdsFilter = (ids: (number | string)[]) => {
    setUrlParam('event_ids', ids.length ? ids.map(String).join(',') : null)
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
    if (eventMetadataError) toast.error(reportError(new Error(eventMetadataError)))
  }, [eventMetadataError])

  useEffect(() => {
    getDuplicateDecks(eventIds.length ? eventIds.map(String).join(',') : undefined)
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
      event_ids: eventIds.length ? eventIds.map(String).join(',') : undefined,
      deck_name: deckName ?? undefined,
      archetype: archetype ?? undefined,
      player: player ?? undefined,
      card: card ?? undefined,
      colors: colors ?? undefined,
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
        toast.error(reportError(e))
      })
      .finally(() => setLoading(false))
  }, [eventIdsParam, deckName, archetype, player, card, colors, sort, order, skip, limit])

  const handleSortHeader = (sortKey: 'date' | 'rank' | 'name' | 'player') => {
    const nextOrder = sort === sortKey ? (order === 'asc' ? 'desc' : 'asc') : sortKey === 'date' || sortKey === 'rank' ? 'desc' : 'asc'
    const params = new URLSearchParams(searchParams)
    params.set('sort', sortKey)
    params.set('order', nextOrder)
    params.delete('page')
    navigate({ search: params.toString() })
  }

  const clearFilters = () => {
    navigate({ pathname: '/decks', search: '' })
  }

  const retryLoad = () => {
    setError(null)
    setLoading(true)
    getDecks({
      event_ids: eventIds.length ? eventIds.map(String).join(',') : undefined,
      deck_name: deckName ?? undefined,
      archetype: archetype ?? undefined,
      player: player ?? undefined,
      card: card ?? undefined,
      colors: colors ?? undefined,
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
        toast.error(reportError(e))
      })
      .finally(() => setLoading(false))
  }

  const hasActiveFilters = !!(eventIds.length || deckName || archetype || player || card || colors)
  const totalPages = Math.ceil(total / limit)

  const getDeckManaCost = (deck: Deck): string => {
    const colors = deck.color_identity ?? []
    if (!colors.length) return ''
    return `{${colors.join('}{')}}`
  }

  const selectedColors = (filters.colors ?? '')
    .split(',')
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean)

  const toggleColorFilter = (value: string) => {
    const set = new Set(selectedColors)
    if (set.has(value)) set.delete(value)
    else set.add(value)
    const next = Array.from(set)
    setFilter('colors', next.length ? next.join(',') : null)
  }

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

      <div className="table-wrap-outer" style={{ marginBottom: '1.5rem' }}>
        <div className="table-wrap" style={{ overflow: 'visible' }}>
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
              width: '100%',
              boxSizing: 'border-box',
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
                value={filters.deck_name ?? ''}
                onChange={(e) => setFilter('deck_name', e.target.value || null)}
                aria-label="Search deck name"
              />
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label htmlFor="decks-archetype">Archetype</label>
              <input
                id="decks-archetype"
                type="text"
                placeholder="Search archetype..."
                value={filters.archetype ?? ''}
                onChange={(e) => setFilter('archetype', e.target.value || null)}
                aria-label="Search archetype"
              />
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label htmlFor="decks-player">Player</label>
              <input
                id="decks-player"
                type="text"
                placeholder="Search player..."
                value={filters.player ?? ''}
                onChange={(e) => setFilter('player', e.target.value || null)}
                aria-label="Search player"
              />
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label htmlFor="decks-card">Card</label>
              <CardSearchInput
                id="decks-card"
                value={filters.card ?? ''}
                onChange={(v) => setFilter('card', v || null)}
                placeholder="Search by card..."
                aria-label="Search by card"
              />
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label>Colors</label>
              <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
                {COLOR_OPTIONS.map((opt) => {
                  const active = selectedColors.includes(opt.value)
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => toggleColorFilter(opt.value)}
                      style={{
                        borderRadius: 999,
                        border: active ? '1px solid var(--accent)' : '1px solid var(--border)',
                        padding: '0.1rem 0.4rem',
                        background: active ? 'var(--accent-soft, var(--accent))' : 'transparent',
                        cursor: 'pointer',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 4,
                        opacity: active ? 1 : 0.9,
                      }}
                      aria-pressed={active}
                      title={opt.title}
                    >
                      <ManaSymbols manaCost={opt.manaCost} size={14} />
                    </button>
                  )
                })}
              </div>
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
          <div className="table-wrap-outer">
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
                {decks.map((d) => {
                  const manaCost = getDeckManaCost(d)
                  return (
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
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                          {d.name}
                          {manaCost && <ManaSymbols manaCost={manaCost} size={16} />}
                        </span>
                        {(!d.mainboard || d.mainboard.length === 0) ? (
                          <span
                            style={{
                              marginLeft: 6,
                              fontSize: '0.7rem',
                              padding: '0.1rem 0.35rem',
                              background: 'rgba(220, 53, 69, 0.2)',
                              borderRadius: 4,
                              color: 'var(--danger, #dc3545)',
                            }}
                            title="No cards in mainboard"
                          >
                            empty
                          </span>
                        ) : duplicateDeckIds.has(d.deck_id) ? (
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
                        ) : null}
                      </td>
                      <td
                        style={{ cursor: 'pointer', color: 'var(--accent)' }}
                        onClick={(e) => { e.stopPropagation(); navigate(`/players/${encodeURIComponent(d.player)}`) }}
                      >
                        {d.player}
                      </td>
                      <td
                        style={{ cursor: 'pointer', color: 'var(--accent)' }}
                        onClick={(e) => { e.stopPropagation(); navigate(`/decks?event_ids=${encodeURIComponent(String(d.event_id))}`) }}
                      >
                        {d.event_name}
                      </td>
                      <td>{d.date}</td>
                      <td>{d.rank || '-'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            </div>
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
