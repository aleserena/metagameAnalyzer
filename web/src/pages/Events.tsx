import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { getEvents, createEvent } from '../api'
import type { EventWithOrigin } from '../api'
import { useAuth } from '../contexts/AuthContext'
import { useFetch } from '../hooks/useFetch'
import { reportError, dateSortKey, ddMmYyToIso, isoToDdMmYy } from '../utils'

/** Coerce value to a string for display; avoid rendering [object Object]. */
function cellStr(v: unknown): string {
  if (v == null) return '—'
  if (typeof v === 'object') return '—'
  return String(v)
}

type SortKey = 'event_name' | 'date' | 'format_id' | 'player_count' | 'store' | 'location'

function normalizeForSort(e: EventWithOrigin, key: SortKey): string | number {
  switch (key) {
    case 'event_name':
      return (typeof e.event_name === 'string' ? e.event_name : '') || 'Unnamed'
    case 'date':
      return dateSortKey(cellStr(e.date))
    case 'format_id':
      return cellStr(e.format_id)
    case 'player_count':
      return typeof e.player_count === 'number' ? e.player_count : 0
    case 'store':
      return cellStr(e.store)
    case 'location':
      return cellStr(e.location)
    default:
      return ''
  }
}

export default function Events() {
  const { user } = useAuth()
  const { data, loading, error, refetch } = useFetch<{ events: EventWithOrigin[] }>(() => getEvents().then((r) => ({ events: r.events })), [])
  const events = data?.events ?? []
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [newStore, setNewStore] = useState('')
  const [newLocation, setNewLocation] = useState('')
  const [newDate, setNewDate] = useState('')
  const [newFormatId, setNewFormatId] = useState('EDH')
  const [newPlayerCount, setNewPlayerCount] = useState(0)
  const [filterName, setFilterName] = useState('')
  const [filterDateIso, setFilterDateIso] = useState('') // YYYY-MM-DD for date picker
  const [filterFormat, setFilterFormat] = useState('')
  const [sortBy, setSortBy] = useState<SortKey>('date')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')

  useEffect(() => {
    if (error) toast.error(reportError(new Error(error)))
  }, [error])

  const handleCreate = () => {
    const name = newName.trim() || 'Unnamed'
    const date = newDate.trim()
    const formatId = newFormatId.trim() || 'EDH'
    if (!newPlayerCount || newPlayerCount < 1) {
      toast.error('Number of players is required (at least 1).')
      return
    }
    setCreating(true)
    createEvent({
      event_name: name,
      date,
      format_id: formatId,
      player_count: newPlayerCount,
      store: newStore.trim(),
      location: newLocation.trim(),
    })
      .then(() => {
        refetch()
        setNewName('')
        setNewStore('')
        setNewLocation('')
        setNewDate('')
        setNewFormatId('EDH')
        setNewPlayerCount(0)
        refetch()
        toast.success('Event created')
      })
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setCreating(false))
  }

  const filteredAndSorted = useMemo(() => {
    let list = events
    const nameLower = filterName.trim().toLowerCase()
    if (nameLower) {
      list = list.filter((e) =>
        (typeof e.event_name === 'string' ? e.event_name : '').toLowerCase().includes(nameLower)
      )
    }
    if (filterDateIso) {
      list = list.filter((e) => ddMmYyToIso(cellStr(e.date)) === filterDateIso)
    }
    if (filterFormat) {
      list = list.filter((e) => cellStr(e.format_id) === filterFormat)
    }
    const dir = sortOrder === 'asc' ? 1 : -1
    return [...list].sort((a, b) => {
      const va = normalizeForSort(a, sortBy)
      const vb = normalizeForSort(b, sortBy)
      const cmp = typeof va === 'number' && typeof vb === 'number'
        ? va - vb
        : String(va).localeCompare(String(vb), undefined, { numeric: true })
      return dir * cmp
    })
  }, [events, filterName, filterDateIso, filterFormat, sortBy, sortOrder])

  const formatOptions = useMemo(() => {
    const set = new Set<string>()
    events.forEach((e) => {
      const f = cellStr(e.format_id).trim()
      if (f) set.add(f)
    })
    return [...set].sort()
  }, [events])

  const hasFilters = Boolean(filterName.trim() || filterDateIso || filterFormat)
  const clearFilters = () => {
    setFilterName('')
    setFilterDateIso('')
    setFilterFormat('')
  }

  const handleSort = (key: SortKey) => {
    if (sortBy === key) {
      setSortOrder((o) => (o === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortBy(key)
      setSortOrder(key === 'date' ? 'desc' : 'asc')
    }
  }

  return (
    <div className="page">
      <h1 className="page-title">Events</h1>
      <p className="muted" style={{ marginBottom: '1.5rem' }}>
        All events. Click an event to see its decks and details.
      </p>

      {user === 'admin' && (
        <section className="card" style={{ marginBottom: '1.5rem' }}>
          <h2 style={{ marginTop: 0 }}>Create event</h2>
          <div className="toolbar toolbar--stack-on-mobile" style={{ gap: '0.75rem', alignItems: 'flex-end' }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span className="label">Name</span>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Event name"
                style={{ minWidth: 200 }}
              />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span className="label">Store</span>
              <input
                type="text"
                value={newStore}
                onChange={(e) => setNewStore(e.target.value)}
                placeholder="Store"
                style={{ minWidth: 120 }}
              />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span className="label">Location</span>
              <input
                type="text"
                value={newLocation}
                onChange={(e) => setNewLocation(e.target.value)}
                placeholder="Location"
                style={{ minWidth: 120 }}
              />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span className="label">Date</span>
              <input
                type="date"
                value={ddMmYyToIso(newDate)}
                onChange={(e) => setNewDate(isoToDdMmYy(e.target.value))}
                style={{ width: 140 }}
              />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span className="label">Format</span>
              <input
                type="text"
                value={newFormatId}
                onChange={(e) => setNewFormatId(e.target.value)}
                placeholder="EDH"
                style={{ width: 80 }}
              />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span className="label">Players (required)</span>
              <input
                type="number"
                min={1}
                value={newPlayerCount || ''}
                onChange={(e) => setNewPlayerCount(parseInt(e.target.value, 10) || 0)}
                placeholder="e.g. 8"
                style={{ width: 70 }}
                required
              />
            </label>
            <button type="button" className="btn btn-primary" onClick={handleCreate} disabled={creating}>
              {creating ? 'Creating…' : 'Create event'}
            </button>
          </div>
        </section>
      )}

      {loading ? (
        <p>Loading events…</p>
      ) : error ? (
        <div className="chart-container" style={{ textAlign: 'center', padding: '2rem' }}>
          <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>{error}</p>
          <button type="button" className="btn" onClick={() => refetch()}>Try again</button>
        </div>
      ) : events.length === 0 ? (
        <div className="chart-container" style={{ textAlign: 'center', padding: '3rem 2rem' }}>
          <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>No events yet.</p>
          {user === 'admin' && (
            <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
              Create an event above or scrape data from the Scrape page.
            </p>
          )}
        </div>
      ) : (
        <>
          <div className="events-filters toolbar toolbar--wrap-on-mobile" style={{ marginBottom: '1rem', gap: '1rem', alignItems: 'flex-end' }}>
            <label className="events-filters-item" style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span className="label">Filter by name</span>
              <input
                type="text"
                value={filterName}
                onChange={(e) => setFilterName(e.target.value)}
                placeholder="Event name contains…"
                style={{ minWidth: 180 }}
              />
            </label>
            <label className="events-filters-item" style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span className="label">Filter by date</span>
              <input
                type="date"
                value={filterDateIso}
                onChange={(e) => setFilterDateIso(e.target.value)}
                style={{ width: 140 }}
              />
            </label>
            <label className="events-filters-item" style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span className="label">Filter by format</span>
              <select
                value={filterFormat}
                onChange={(e) => setFilterFormat(e.target.value)}
                style={{ minWidth: 100 }}
              >
                <option value="">All formats</option>
                {formatOptions.map((f) => (
                  <option key={f} value={f}>{f}</option>
                ))}
              </select>
            </label>
            {hasFilters && (
              <button type="button" className="btn" onClick={clearFilters}>
                Clear filters
              </button>
            )}
          </div>
          {hasFilters && (
            <p className="muted" style={{ marginBottom: '0.75rem' }}>
              Showing {filteredAndSorted.length} of {events.length} events
            </p>
          )}
          <div className="table-wrap-outer">
            <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th
                    scope="col"
                    className="sortable"
                    style={{ cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('event_name')}
                    title="Sort by event name"
                    aria-sort={sortBy === 'event_name' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : undefined}
                  >
                    Event {sortBy === 'event_name' && (sortOrder === 'asc' ? '↑' : '↓')}
                  </th>
                  <th
                    scope="col"
                    className="sortable"
                    style={{ cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('date')}
                    title="Sort by date"
                    aria-sort={sortBy === 'date' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : undefined}
                  >
                    Date {sortBy === 'date' && (sortOrder === 'asc' ? '↑' : '↓')}
                  </th>
                  <th
                    scope="col"
                    className="sortable"
                    style={{ cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('format_id')}
                    title="Sort by format"
                    aria-sort={sortBy === 'format_id' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : undefined}
                  >
                    Format {sortBy === 'format_id' && (sortOrder === 'asc' ? '↑' : '↓')}
                  </th>
                  <th
                    scope="col"
                    className="sortable"
                    style={{ cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('player_count')}
                    title="Sort by players"
                    aria-sort={sortBy === 'player_count' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : undefined}
                  >
                    Players {sortBy === 'player_count' && (sortOrder === 'asc' ? '↑' : '↓')}
                  </th>
                  <th
                    scope="col"
                    className="sortable"
                    style={{ cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('store')}
                    title="Sort by store"
                    aria-sort={sortBy === 'store' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : undefined}
                  >
                    Store {sortBy === 'store' && (sortOrder === 'asc' ? '↑' : '↓')}
                  </th>
                  <th
                    scope="col"
                    className="sortable"
                    style={{ cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('location')}
                    title="Sort by location"
                    aria-sort={sortBy === 'location' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : undefined}
                  >
                    Location {sortBy === 'location' && (sortOrder === 'asc' ? '↑' : '↓')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {filteredAndSorted.map((e) => (
                <tr key={String(e.event_id)}>
                  <td>
                    <Link to={`/events/${encodeURIComponent(String(e.event_id))}`} style={{ color: 'var(--accent)', fontWeight: 500 }}>
                      {(typeof e.event_name === 'string' && e.event_name.trim()) ? e.event_name : 'Unnamed'}
                    </Link>
                  </td>
                  <td>{cellStr(e.date)}</td>
                  <td>{cellStr(e.format_id) || '—'}</td>
                  <td>{typeof e.player_count === 'number' ? e.player_count : '—'}</td>
                  <td>{cellStr(e.store) || '—'}</td>
                  <td>{cellStr(e.location) || '—'}</td>
                </tr>
              ))}
              </tbody>
            </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
