import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { getMetagame, getEvents, getDateRange } from '../api'
import type { MetagameReport, Event } from '../types'
import CardHover from '../components/CardHover'
import EventSelector from '../components/EventSelector'
import { Skeleton, SkeletonList } from '../components/Skeleton'
import { reportError } from '../utils'

export default function Dashboard() {
  const [metagame, setMetagame] = useState<MetagameReport | null>(null)
  const [events, setEvents] = useState<Event[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [ignoreLands, setIgnoreLands] = useState(false)
  const [eventIds, setEventIds] = useState<number[]>([])
  const [maxDate, setMaxDate] = useState<string | null>(null)
  const [lastEventDate, setLastEventDate] = useState<string | null>(null)

  useEffect(() => {
    getEvents().then((r) => setEvents(r.events))
    getDateRange().then((r) => {
      setMaxDate(r.max_date)
      setLastEventDate(r.last_event_date)
    })
  }, [])

  useEffect(() => {
    setLoading(true)
    const eventIdsParam = eventIds.length ? eventIds.join(',') : undefined
    getMetagame(false, ignoreLands, undefined, undefined, undefined, eventIdsParam)
      .then(setMetagame)
      .catch((e) => {
        setError(e.message)
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
        <div className="chart-container" style={{ textAlign: 'center', padding: '2rem' }}>
          <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>{error}</p>
          <button
            type="button"
            className="btn"
            onClick={() => {
              setError(null)
              setLoading(true)
              const eventIdsParam = eventIds.length ? eventIds.join(',') : undefined
              getMetagame(false, ignoreLands, undefined, undefined, undefined, eventIdsParam)
                .then(setMetagame)
                .catch((e) => {
                  setError(e.message)
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

  const summary = metagame?.summary ?? { total_decks: 0, unique_commanders: 0, unique_archetypes: 0 }
  const topCommanders = metagame?.commander_distribution?.slice(0, 5) ?? []
  const topArchetypes = metagame?.archetype_distribution?.slice(0, 5) ?? []
  const topCards = metagame?.top_cards_main?.slice(0, 5) ?? []
  const recentEvents = [...events].sort((a, b) => b.date.localeCompare(a.date)).slice(0, 5)
  const isEmpty = summary.total_decks === 0

  if (isEmpty) {
    return (
      <div className="chart-container" style={{ textAlign: 'center', padding: '3rem 2rem', maxWidth: 480, margin: '0 auto' }}>
        <p style={{ color: 'var(--text-muted)', marginBottom: '1rem', fontSize: '1.1rem' }}>
          No deck data yet
        </p>
        <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
          Load or scrape data from MTGTop8 to see the metagame analysis, top commanders, and more.
        </p>
        <Link to="/scrape" className="btn" style={{ textDecoration: 'none' }}>
          Load or scrape data
        </Link>
      </div>
    )
  }

  return (
    <div style={{ opacity: loading ? 0.6 : 1, transition: 'opacity 0.2s' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
        <h1 className="page-title" style={{ margin: 0 }}>Dashboard</h1>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'stretch', gap: '1rem', marginBottom: '2rem' }}>
        <div className="card-grid" style={{ flex: '1 1 auto', minWidth: 0, marginBottom: 0 }}>
          <div className="stat-card">
            <div className="value">{summary.total_decks}</div>
            <div className="label">Total Decks</div>
          </div>
          <div className="stat-card">
            <div className="value">{summary.unique_commanders}</div>
            <div className="label">Unique Commanders</div>
          </div>
          <div className="stat-card">
            <div className="value">{summary.unique_archetypes}</div>
            <div className="label">Archetypes</div>
          </div>
        </div>
        <div
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

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1.5rem' }}>
        <div className="chart-container">
          <h3 style={{ margin: '0 0 1rem' }}>Top Commanders</h3>
          {topCommanders.length ? (
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {topCommanders.map((c, i) => (
                <li key={c.commander} style={{ padding: '0.5rem 0', borderBottom: '1px solid var(--border)', display: 'flex', gap: '0.5rem', alignItems: 'baseline' }}>
                  <span style={{ color: 'var(--text-muted)', minWidth: 18 }}>{i + 1}.</span>
                  <Link to={`/decks?deck_name=${encodeURIComponent(c.commander)}`} style={{ color: 'var(--accent)' }}>
                    {c.commander}
                  </Link>
                  <span style={{ color: 'var(--text-muted)', marginLeft: 'auto', fontSize: '0.875rem', whiteSpace: 'nowrap' }}>
                    {c.count} decks ({c.pct}%)
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

      <div className="chart-container" style={{ marginTop: '1rem' }}>
        <h3 style={{ margin: '0 0 1rem' }}>Recent Events</h3>
        {recentEvents.length ? (
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {recentEvents.map((e) => (
              <li key={`${e.event_id}-${e.date}`} style={{ padding: '0.5rem 0', borderBottom: '1px solid var(--border)' }}>
                <Link to={`/decks?event_ids=${e.event_id}`} style={{ color: 'var(--accent)' }}>
                  {e.event_name}
                </Link>
                <span style={{ color: 'var(--text-muted)', marginLeft: '0.5rem' }}>{e.date}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p style={{ color: 'var(--text-muted)' }}>No events. Load or scrape data first.</p>
        )}
      </div>

      <div style={{ marginTop: '1.5rem', display: 'flex', gap: '1rem' }}>
        <Link to="/metagame" className="btn">View Metagame</Link>
        <Link to="/decks" className="btn">Browse Decks</Link>
        <Link to="/players" className="btn">Player Leaderboard</Link>
      </div>
    </div>
  )
}
