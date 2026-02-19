import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getMetagame, getEvents, getDateRange } from '../api'
import type { MetagameReport, Event } from '../types'
import CardHover from '../components/CardHover'
import { dateMinusDays } from '../utils'

export default function Dashboard() {
  const [metagame, setMetagame] = useState<MetagameReport | null>(null)
  const [events, setEvents] = useState<Event[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [ignoreLands, setIgnoreLands] = useState(false)
  const [dateFrom, setDateFrom] = useState<string | null>(null)
  const [dateTo, setDateTo] = useState<string | null>(null)
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
    getMetagame(false, ignoreLands, dateFrom, dateTo)
      .then(setMetagame)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [ignoreLands, dateFrom, dateTo])

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

  if (!metagame && loading) return <div className="loading">Loading...</div>
  if (error) return <div className="error">{error}</div>

  const summary = metagame?.summary ?? { total_decks: 0, unique_commanders: 0, unique_archetypes: 0 }
  const topCommanders = metagame?.commander_distribution?.slice(0, 5) ?? []
  const topCards = metagame?.top_cards_main?.slice(0, 5) ?? []
  const recentEvents = [...events].sort((a, b) => b.date.localeCompare(a.date)).slice(0, 5)

  return (
    <div style={{ opacity: loading ? 0.6 : 1, transition: 'opacity 0.2s' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <h1 className="page-title" style={{ margin: 0 }}>Dashboard</h1>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center' }}>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Date range:</span>
            <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('all')}>All time</button>
            <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('month')}>Last month</button>
            <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('2weeks')}>Last 2 weeks</button>
            <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('lastEvent')}>Last event</button>
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
            <input type="checkbox" checked={ignoreLands} onChange={(e) => setIgnoreLands(e.target.checked)} />
            Ignore lands
          </label>
        </div>
      </div>

      <div className="card-grid" style={{ marginBottom: '2rem' }}>
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

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
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
          <h3 style={{ margin: '0 0 1rem' }}>Top Cards</h3>
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
                <Link to={`/decks?event_id=${e.event_id}`} style={{ color: 'var(--accent)' }}>
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
