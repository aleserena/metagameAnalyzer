import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { getPlayers } from '../api'
import { useEventMetadata } from '../hooks/useEventMetadata'
import type { PlayerStats } from '../types'
import Skeleton from '../components/Skeleton'
import { useFetch } from '../hooks/useFetch'
import { getDateRangeFromPreset, reportError } from '../utils'
import type { DatePreset } from '../utils'

type SortKey = 'player' | 'wins' | 'top2' | 'top4' | 'top8' | 'points' | 'deck_count'

export default function Players() {
  const { maxDate, lastEventDate, error: eventMetadataError } = useEventMetadata()
  const [sortBy, setSortBy] = useState<SortKey>('wins')
  const [sortDesc, setSortDesc] = useState(true)
  const [dateFrom, setDateFrom] = useState<string | null>(null)
  const [dateTo, setDateTo] = useState<string | null>(null)
  const [nameFilter, setNameFilter] = useState('')

  const { data, loading, error, refetch } = useFetch<{ players: PlayerStats[] }>(
    () => getPlayers(dateFrom, dateTo).then((r) => ({ players: r.players })),
    [dateFrom, dateTo]
  )
  const players = data?.players ?? []

  useEffect(() => {
    if (eventMetadataError) toast.error(reportError(new Error(eventMetadataError)))
  }, [eventMetadataError])

  useEffect(() => {
    if (error) toast.error(reportError(new Error(error)))
  }, [error])

  const setPreset = (preset: DatePreset) => {
    const { dateFrom: from, dateTo: to } = getDateRangeFromPreset(maxDate, lastEventDate, preset)
    setDateFrom(from)
    setDateTo(to)
  }

  const handleSort = (key: SortKey) => {
    if (sortBy === key) setSortDesc((d) => !d)
    else {
      setSortBy(key)
      setSortDesc(true)
    }
  }

  const sorted = [...players].sort((a, b) => {
    const va = a[sortBy]
    const vb = b[sortBy]
    const cmp = typeof va === 'string' ? va.localeCompare(vb as string) : (va as number) - (vb as number)
    return sortDesc ? -cmp : cmp
  })

  // Position in leaderboard (1-based) for current date range and sort; unchanged when filtering by name
  const positionByPlayer = new Map<string, number>()
  sorted.forEach((p, i) => positionByPlayer.set(p.player, i + 1))

  const nameFilterLower = nameFilter.trim().toLowerCase()
  const filtered = nameFilterLower
    ? sorted.filter((p) => p.player.toLowerCase().includes(nameFilterLower))
    : sorted

  if (loading) {
    return (
      <div>
        <div style={{ marginBottom: '1.5rem' }}>
          <Skeleton width={200} height={28} style={{ marginBottom: '1rem' }} />
          <Skeleton width={300} height={32} />
        </div>
        <div className="table-wrap-outer">
          <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th><Skeleton width={56} height={14} /></th>
                <th><Skeleton width={100} height={14} /></th>
                <th><Skeleton width={60} height={14} /></th>
                <th><Skeleton width={50} height={14} /></th>
                <th><Skeleton width={50} height={14} /></th>
                <th><Skeleton width={50} height={14} /></th>
                <th><Skeleton width={60} height={14} /></th>
                <th><Skeleton width={80} height={14} /></th>
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: 10 }).map((_, i) => (
                <tr key={i}>
                  <td><Skeleton width={32} height={16} /></td>
                  <td><Skeleton width="70%" height={16} /></td>
                  <td><Skeleton width={40} height={16} /></td>
                  <td><Skeleton width={30} height={16} /></td>
                  <td><Skeleton width={30} height={16} /></td>
                  <td><Skeleton width={30} height={16} /></td>
                  <td><Skeleton width={40} height={16} /></td>
                  <td><Skeleton width={50} height={16} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      </div>
    )
  }
  if (error) {
    return (
      <div>
        <h1 className="page-title" style={{ margin: 0 }}>Player Leaderboard</h1>
        <div className="chart-container" style={{ textAlign: 'center', padding: '2rem', marginTop: '1.5rem' }}>
          <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>{error}</p>
          <button type="button" className="btn" onClick={() => refetch()}>
            Try again
          </button>
        </div>
      </div>
    )
  }

  if (sorted.length === 0) {
    return (
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
          <h1 className="page-title" style={{ margin: 0 }}>Player Leaderboard</h1>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Date range:</span>
            <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('all')}>All time</button>
            <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('thisYear')}>This year</button>
            <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('6months')}>6 months</button>
            <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('2months')}>2 months</button>
            <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('month')}>Last month</button>
            <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('2weeks')}>Last 2 weeks</button>
            <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('lastEvent')}>Last event</button>
          </div>
        </div>
        <div className="chart-container" style={{ textAlign: 'center', padding: '3rem 2rem' }}>
          <p style={{ color: 'var(--text-muted)', marginBottom: '1rem', fontSize: '1.1rem' }}>No players found</p>
          <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
            Load or scrape deck data first to see the player leaderboard.
          </p>
          <Link to="/scrape" className="btn" style={{ textDecoration: 'none' }}>Load or scrape data</Link>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <h1 className="page-title" style={{ margin: 0 }}>Player Leaderboard</h1>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <label htmlFor="players-name-filter" style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Filter by name:</label>
            <input
              id="players-name-filter"
              type="text"
              value={nameFilter}
              onChange={(e) => setNameFilter(e.target.value)}
              placeholder="Search player..."
              style={{ width: 160, padding: '0.25rem 0.5rem', fontSize: '0.875rem' }}
              aria-label="Filter by player name"
            />
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Date range:</span>
            <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('all')}>
              All time
            </button>
          <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('thisYear')}>
            This year
          </button>
          <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('6months')}>
            6 months
          </button>
          <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('2months')}>
            2 months
          </button>
          <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('month')}>
            Last month
          </button>
          <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('2weeks')}>
            Last 2 weeks
          </button>
          <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('lastEvent')}>
            Last event
          </button>
          </div>
        </div>
      </div>

      <div className="table-wrap-outer">
        <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Position</th>
              <th style={{ cursor: 'pointer' }} onClick={() => handleSort('player')}>
                Player {sortBy === 'player' && (sortDesc ? '↓' : '↑')}
              </th>
              <th style={{ cursor: 'pointer' }} onClick={() => handleSort('wins')}>
                Wins {sortBy === 'wins' && (sortDesc ? '↓' : '↑')}
              </th>
              <th style={{ cursor: 'pointer' }} onClick={() => handleSort('top2')}>
                Top 2 {sortBy === 'top2' && (sortDesc ? '↓' : '↑')}
              </th>
              <th style={{ cursor: 'pointer' }} onClick={() => handleSort('top4')}>
                Top 4 {sortBy === 'top4' && (sortDesc ? '↓' : '↑')}
              </th>
              <th style={{ cursor: 'pointer' }} onClick={() => handleSort('top8')}>
                Top 8 {sortBy === 'top8' && (sortDesc ? '↓' : '↑')}
              </th>
              <th style={{ cursor: 'pointer' }} onClick={() => handleSort('points')}>
                Points {sortBy === 'points' && (sortDesc ? '↓' : '↑')}
              </th>
              <th style={{ cursor: 'pointer' }} onClick={() => handleSort('deck_count')}>
                Decks {sortBy === 'deck_count' && (sortDesc ? '↓' : '↑')}
              </th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={8} style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '1.5rem' }}>
                  No players match the filter.
                </td>
              </tr>
            ) : (
              filtered.map((p) => (
                <tr key={p.player}>
                  <td>{positionByPlayer.get(p.player) ?? '—'}</td>
                  <td>
                    <Link to={`/players/${p.player_id != null ? p.player_id : encodeURIComponent(p.player)}`} className="nav-link" style={{ padding: 0 }}>
                      {p.player}
                    </Link>
                  </td>
                  <td>{p.wins}</td>
                  <td>{p.top2}</td>
                  <td>{p.top4}</td>
                  <td>{p.top8}</td>
                  <td>{p.points.toFixed(1)}</td>
                  <td>{p.deck_count}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        </div>
      </div>

    </div>
  )
}
