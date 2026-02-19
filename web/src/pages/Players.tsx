import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getPlayers, getDateRange, getPlayerAliases, addPlayerAlias, removePlayerAlias } from '../api'
import type { PlayerStats } from '../types'
import Skeleton from '../components/Skeleton'
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
  const [aliasesOpen, setAliasesOpen] = useState(false)
  const [aliases, setAliases] = useState<Record<string, string>>({})
  const [newAlias, setNewAlias] = useState('')
  const [newCanonical, setNewCanonical] = useState('')

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

  useEffect(() => {
    getPlayerAliases().then((r) => setAliases(r.aliases))
  }, [aliasesOpen])

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

  if (loading) {
    return (
      <div>
        <div style={{ marginBottom: '1.5rem' }}>
          <Skeleton width={200} height={28} style={{ marginBottom: '1rem' }} />
          <Skeleton width={300} height={32} />
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
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
    )
  }
  if (error) return <div className="error">{error}</div>

  if (sorted.length === 0) {
    return (
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
          <h1 className="page-title" style={{ margin: 0 }}>Player Leaderboard</h1>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Date range:</span>
            <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('all')}>All time</button>
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

      <div className="chart-container" style={{ marginTop: '1.5rem' }}>
        <button
          type="button"
          onClick={() => setAliasesOpen((o) => !o)}
          style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: '0.9rem' }}
        >
          {aliasesOpen ? '▼' : '▶'} Manage player aliases (merge duplicate names)
        </button>
        {aliasesOpen && (
          <div style={{ marginTop: '1rem' }}>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '1rem' }}>
              Map alternate names to a canonical name. E.g. &quot;Pablo Tomas Pesci&quot; → &quot;Tomas Pesci&quot; merges stats.
            </p>
            {Object.keys(aliases).length > 0 && (
              <div style={{ marginBottom: '1rem' }}>
                <div style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.5rem' }}>Current aliases:</div>
                {Object.entries(aliases).map(([alias, canonical]) => (
                  <div
                    key={alias}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      padding: '0.2rem 0',
                      fontSize: '0.9rem',
                    }}
                  >
                    <span>{alias}</span>
                    <span style={{ color: 'var(--text-muted)' }}>→</span>
                    <Link to={`/players/${encodeURIComponent(canonical)}`} style={{ color: 'var(--accent)' }}>
                      {canonical}
                    </Link>
                    <button
                      type="button"
                      onClick={() => removePlayerAlias(alias).then((r) => (setAliases(r.aliases), setPlayers([]), getPlayers(dateFrom, dateTo).then((x) => setPlayers(x.players))))}
                      style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.8rem' }}
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
              <input
                type="text"
                placeholder="Alias (e.g. Pablo Tomas Pesci)"
                value={newAlias}
                onChange={(e) => setNewAlias(e.target.value)}
                style={{ padding: '0.35rem 0.5rem', minWidth: 180 }}
              />
              <span style={{ color: 'var(--text-muted)' }}>→</span>
              <input
                type="text"
                placeholder="Canonical (e.g. Tomas Pesci)"
                value={newCanonical}
                onChange={(e) => setNewCanonical(e.target.value)}
                style={{ padding: '0.35rem 0.5rem', minWidth: 180 }}
              />
              <button
                type="button"
                className="btn"
                style={{ padding: '0.35rem 0.75rem' }}
                onClick={() => {
                  if (!newAlias.trim() || !newCanonical.trim()) return
                  addPlayerAlias(newAlias.trim(), newCanonical.trim())
                    .then((r) => {
                      setAliases(r.aliases)
                      setNewAlias('')
                      setNewCanonical('')
                      getPlayers(dateFrom, dateTo).then((x) => setPlayers(x.players))
                    })
                }}
              >
                Add merge
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
