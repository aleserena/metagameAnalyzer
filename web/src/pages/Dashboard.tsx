import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { getMetagame } from '../api'
import type { MetagameReport, Event } from '../types'
import { useEventMetadata } from '../hooks/useEventMetadata'
import CardHover from '../components/CardHover'
import EventSelector from '../components/EventSelector'
import { Skeleton, SkeletonList } from '../components/Skeleton'
import { reportError } from '../utils'

export default function Dashboard() {
  const { events, maxDate, lastEventDate, error: eventMetadataError } = useEventMetadata()
  const [metagame, setMetagame] = useState<MetagameReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [ignoreLands, setIgnoreLands] = useState(false)
  const [eventIds, setEventIds] = useState<(number | string)[]>([])

  useEffect(() => {
    if (eventMetadataError) toast.error(reportError(new Error(eventMetadataError)))
  }, [eventMetadataError])

  useEffect(() => {
    setLoading(true)
    setError(null)
    const eventIdsParam = eventIds.length ? eventIds.map(String).join(',') : undefined
    getMetagame(false, ignoreLands, undefined, undefined, undefined, eventIdsParam)
      .then(setMetagame)
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e))
        toast.error(reportError(e))
      })
      .finally(() => setLoading(false))
  }, [ignoreLands, eventIds])

  if (!metagame && loading) {
    return (
      <div>
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
          <Skeleton width={80} height={32} />
          <Skeleton width={100} height={32} />
          <Skeleton width={120} height={32} />
          <Skeleton width={100} height={32} />
        </div>
        <div className="card-grid" style={{ marginBottom: '2rem' }}>
          {[1, 2, 3].map((i) => (
            <div key={i} className="stat-card">
              <Skeleton width={60} height={28} style={{ marginBottom: '0.5rem' }} />
              <Skeleton width={100} height={14} />
            </div>
          ))}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1.5rem' }}>
          {[1, 2, 3].map((i) => (
            <div key={i} className="chart-container">
              <Skeleton width={140} height={24} style={{ marginBottom: '1rem' }} />
              <SkeletonList items={5} />
            </div>
          ))}
        </div>
      </div>
    )
  }
  if (error) {
    return (
      <div>
        <h1 className="page-title">Dashboard</h1>
        <div className="chart-container" style={{ textAlign: 'center', padding: '2rem', maxWidth: 420, margin: '0 auto' }}>
          <p style={{ color: 'var(--text-muted)', marginBottom: '0.75rem' }}>{error}</p>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '1.25rem' }}>
            If you just ran <code style={{ background: 'var(--bg)', padding: '0.15rem 0.4rem', borderRadius: 4 }}>npm run dev</code>, wait a few seconds for the API to start, then click Try again or refresh.
          </p>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              setError(null)
              setLoading(true)
              const eventIdsParam = eventIds.length ? eventIds.map(String).join(',') : undefined
              getMetagame(false, ignoreLands, undefined, undefined, undefined, eventIdsParam)
                .then(setMetagame)
                .catch((e) => {
                  setError(e instanceof Error ? e.message : String(e))
                  toast.error(reportError(e))
                })
                .finally(() => setLoading(false))
            }}
          >
            Try again
          </button>
        </div>
      </div>
    )
  }

  const summary = metagame?.summary ?? { total_decks: 0, unique_players: 0, unique_archetypes: 0 }
  const topPlayers = metagame?.top_players?.slice(0, 5) ?? []
  const topArchetypes = metagame?.archetype_distribution?.slice(0, 5) ?? []
  const topCards = metagame?.top_cards_main?.slice(0, 5) ?? []
  // Parse DD/MM/YY (or DD/MM/YYYY) to YYYYMMDD for chronological sort; invalid/empty => 0 (sort last)
  const eventDateKey = (e: Event) => {
    const s = (e.date || '').trim()
    if (!s) return 0
    const parts = s.split('/').map((p) => p.trim())
    if (parts.length < 3) return 0
    const day = parseInt(parts[0], 10)
    const month = parseInt(parts[1], 10)
    let y = parseInt(parts[2], 10)
    if (isNaN(day) || isNaN(month) || isNaN(y)) return 0
    if (y < 100) y += 2000 // 24 -> 2024
    return y * 10000 + month * 100 + day
  }
  const recentEvents = [...events]
    .sort((a, b) => eventDateKey(b) - eventDateKey(a))
    .slice(0, 5)
  const isEmpty = summary.total_decks === 0

  if (isEmpty) {
    return (
      <div className="chart-container" style={{ textAlign: 'center', padding: '3rem 2rem', maxWidth: 480, margin: '0 auto' }}>
        <p style={{ color: 'var(--text-muted)', marginBottom: '1rem', fontSize: '1.1rem' }}>
          No deck data yet
        </p>
        <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
          Load or scrape data from MTGTop8 to see the metagame analysis, top players, and more.
        </p>
        <Link to="/scrape" className="btn" style={{ textDecoration: 'none' }}>
          Load or scrape data
        </Link>
      </div>
    )
  }

  return (
    <div style={{ opacity: loading ? 0.6 : 1, transition: 'opacity 0.2s' }}>
      <div className="toolbar toolbar--stack-on-mobile dashboard-header" style={{ marginBottom: '1rem' }}>
        <h1 className="page-title" style={{ margin: 0 }}>Dashboard</h1>
      </div>

      <div className="toolbar toolbar--stack-on-mobile" style={{ alignItems: 'stretch', marginBottom: '2rem', gap: '1rem' }}>
        <div className="card-grid dashboard-stat-grid" style={{ flex: '1 1 auto', minWidth: 0, marginBottom: 0 }}>
          <Link to="/decks" className="stat-card" style={{ textDecoration: 'none', color: 'inherit', display: 'block' }}>
            <div className="value">{summary.total_decks}</div>
            <div className="label">Total Decks</div>
          </Link>
          <Link to="/events" className="stat-card" style={{ textDecoration: 'none', color: 'inherit', display: 'block' }}>
            <div className="value">{events.length}</div>
            <div className="label">Events</div>
          </Link>
          <Link to="/players" className="stat-card" style={{ textDecoration: 'none', color: 'inherit', display: 'block' }}>
            <div className="value">{summary.unique_players}</div>
            <div className="label">Unique Players</div>
          </Link>
          <Link to="/archetypes" className="stat-card" style={{ textDecoration: 'none', color: 'inherit', display: 'block' }}>
            <div className="value">{summary.unique_archetypes}</div>
            <div className="label">Archetypes</div>
          </Link>
        </div>
        <div
          className="dashboard-events-filter"
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '0.5rem',
            alignItems: 'center',
            padding: '0.5rem 0.75rem',
            background: 'var(--bg)',
            border: '1px solid var(--border)',
            borderRadius: 8,
            fontSize: '0.8125rem',
          }}
        >
          <EventSelector
            events={events}
            selectedIds={eventIds}
            onChange={setEventIds}
            showDatePresets
            maxDate={maxDate}
            lastEventDate={lastEventDate}
          />
        </div>
      </div>

      <div className="dashboard-charts-grid">
        <div className="chart-container">
          <h3 style={{ margin: '0 0 1rem' }}>Top Players</h3>
          {topPlayers.length ? (
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {topPlayers.map((p, i) => (
                <li key={p.player} style={{ padding: '0.5rem 0', borderBottom: '1px solid var(--border)', display: 'flex', gap: '0.5rem', alignItems: 'baseline' }}>
                  <span style={{ color: 'var(--text-muted)', minWidth: 18 }}>{i + 1}.</span>
                  <Link to={`/players/${encodeURIComponent(p.player)}`} style={{ color: 'var(--accent)' }}>
                    {p.player}
                  </Link>
                  <span style={{ color: 'var(--text-muted)', marginLeft: 'auto', fontSize: '0.875rem', whiteSpace: 'nowrap' }}>
                    {p.wins} win{p.wins !== 1 ? 's' : ''}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p style={{ color: 'var(--text-muted)' }}>No data</p>
          )}
        </div>

        <div className="chart-container">
          <h3 style={{ margin: '0 0 1rem' }}>Top Archetypes</h3>
          {topArchetypes.length ? (
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {topArchetypes.map((a, i) => (
                <li key={a.archetype} style={{ padding: '0.5rem 0', borderBottom: '1px solid var(--border)', display: 'flex', gap: '0.5rem', alignItems: 'baseline' }}>
                  <span style={{ color: 'var(--text-muted)', minWidth: 18 }}>{i + 1}.</span>
                  <Link to={`/decks?archetype=${encodeURIComponent(a.archetype)}`} style={{ color: 'var(--accent)' }}>
                    {a.archetype}
                  </Link>
                  <span style={{ color: 'var(--text-muted)', marginLeft: 'auto', fontSize: '0.875rem', whiteSpace: 'nowrap' }}>
                    {a.count} decks ({a.pct}%)
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p style={{ color: 'var(--text-muted)' }}>No data</p>
          )}
        </div>

        <div className="chart-container">
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
            <h3 style={{ margin: 0 }}>Top Cards</h3>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.875rem' }}>
              <input
                type="checkbox"
                checked={ignoreLands}
                onChange={(e) => setIgnoreLands(e.target.checked)}
                aria-label="Ignore lands"
              />
              Ignore lands
            </label>
          </div>
          {topCards.length ? (
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {topCards.map((c, i) => (
                <li key={c.card} style={{ padding: '0.5rem 0', borderBottom: '1px solid var(--border)', display: 'flex', gap: '0.5rem', alignItems: 'baseline' }}>
                  <span style={{ color: 'var(--text-muted)', minWidth: 18 }}>{i + 1}.</span>
                  <CardHover cardName={c.card} linkTo>{c.card}</CardHover>
                  <span style={{ color: 'var(--text-muted)', marginLeft: 'auto', fontSize: '0.875rem', whiteSpace: 'nowrap' }}>
                    {c.decks} decks ({c.play_rate_pct}%)
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p style={{ color: 'var(--text-muted)' }}>No data</p>
          )}
        </div>
      </div>

      <div className="chart-container dashboard-recent-events" style={{ marginTop: '1rem' }}>
        <h3 style={{ margin: '0 0 1rem' }}>Recent Events</h3>
        {recentEvents.length ? (
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {recentEvents.map((e) => (
              <li key={`${e.event_id}-${e.date}`} style={{ padding: '0.5rem 0', borderBottom: '1px solid var(--border)' }}>
                <Link to={`/events/${encodeURIComponent(String(e.event_id))}`} style={{ color: 'var(--accent)' }}>
                  {(typeof e.event_name === 'string' && e.event_name.trim()) ? e.event_name : 'Unnamed'}
                </Link>
                <div style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginTop: '0.15rem' }}>
                  {[e.date, e.store, e.location].filter(Boolean).join(' · ')}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p style={{ color: 'var(--text-muted)' }}>No events. Load or scrape data first.</p>
        )}
      </div>

    </div>
  )
}
