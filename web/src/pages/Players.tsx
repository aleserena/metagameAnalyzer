import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getPlayers, getDateRange } from '../api'
import type { PlayerStats } from '../types'
import { dateMinusDays } from '../utils'

type SortKey = 'player' | 'wins' | 'top2' | 'top4' | 'top8' | 'points' | 'deck_count'

export default function Players() {
  const [players, setPlayers] = useState<PlayerStats[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sortBy, setSortBy] = useState<SortKey>('wins')
  const [sortDesc, setSortDesc] = useState(true)
  const [dateFrom, setDateFrom] = useState<string | null>(null)
  const [dateTo, setDateTo] = useState<string | null>(null)
  const [maxDate, setMaxDate] = useState<string | null>(null)
  const [lastEventDate, setLastEventDate] = useState<string | null>(null)

  useEffect(() => {
    getDateRange().then((r) => {
      setMaxDate(r.max_date)
      setLastEventDate(r.last_event_date)
    })
  }, [])

  useEffect(() => {
    setLoading(true)
    getPlayers(dateFrom, dateTo)
      .then((r) => setPlayers(r.players))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [dateFrom, dateTo])

  const setPreset = (preset: 'all' | '2weeks' | 'month' | 'lastEvent') => {
    if (preset === 'all' || !maxDate) {
      setDateFrom(null)
      setDateTo(null)
      return
    }
    if (preset === 'lastEvent' && lastEventDate) {
      setDateFrom(lastEventDate)
      setDateTo(lastEventDate)
      return
    }
    setDateTo(maxDate)
    setDateFrom(preset === '2weeks' ? dateMinusDays(maxDate, 14) : dateMinusDays(maxDate, 30))
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

  if (loading) return <div className="loading">Loading...</div>
  if (error) return <div className="error">{error}</div>

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <h1 className="page-title" style={{ margin: 0 }}>Player Leaderboard</h1>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Date range:</span>
          <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('all')}>
            All time
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

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
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
            {sorted.map((p) => (
              <tr key={p.player}>
                <td>
                  <Link to={`/players/${encodeURIComponent(p.player)}`} className="nav-link" style={{ padding: 0 }}>
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
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
