import { useEffect, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts'
import { getMetagame, getDateRange, getFormatInfo, getEvents } from '../api'
import CardHover from '../components/CardHover'
import type { MetagameReport, Event } from '../types'
import { dateMinusDays } from '../utils'

const COLORS = ['#1d9bf0', '#00ba7c', '#f7931a', '#e91e63', '#9c27b0', '#00bcd4', '#ff9800', '#4caf50']

export default function Metagame() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [metagame, setMetagame] = useState<MetagameReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [placementWeighted, setPlacementWeighted] = useState(false)
  const [ignoreLands, setIgnoreLands] = useState(false)
  const [dateFrom, setDateFrom] = useState<string | null>(() => searchParams.get('date_from'))
  const [dateTo, setDateTo] = useState<string | null>(() => searchParams.get('date_to'))
  const [eventId, setEventId] = useState<number | null>(() => {
    const id = searchParams.get('event_id')
    return id ? parseInt(id, 10) : null
  })
  const [topCardsPage, setTopCardsPage] = useState(0)

  useEffect(() => {
    setDateFrom(searchParams.get('date_from'))
    setDateTo(searchParams.get('date_to'))
    const id = searchParams.get('event_id')
    setEventId(id ? parseInt(id, 10) : null)
  }, [searchParams])
  const [maxDate, setMaxDate] = useState<string | null>(null)
  const [lastEventDate, setLastEventDate] = useState<string | null>(null)
  const [formatName, setFormatName] = useState<string | null>(null)
  const [events, setEvents] = useState<Event[]>([])

  useEffect(() => {
    getDateRange().then((r) => {
      setMaxDate(r.max_date)
      setLastEventDate(r.last_event_date)
    })
    getFormatInfo().then((r) => setFormatName(r.format_name))
    getEvents().then((r) => setEvents(r.events))
  }, [])

  useEffect(() => {
    setLoading(true)
    getMetagame(placementWeighted, ignoreLands, dateFrom, dateTo, eventId)
      .then(setMetagame)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [placementWeighted, ignoreLands, dateFrom, dateTo, eventId])

  const setEventFilter = (id: number | null) => {
    setEventId(id)
    const p = new URLSearchParams(searchParams)
    if (id != null) p.set('event_id', String(id))
    else p.delete('event_id')
    setSearchParams(p)
  }

  if (!metagame && loading) return <div className="loading">Loading...</div>
  if (error) return <div className="error">{error}</div>

  const TOP_CARDS_PER_PAGE = 50

  const commanders = metagame?.commander_distribution ?? []
  const archetypes = metagame?.archetype_distribution ?? []
  const topMain = metagame?.top_cards_main ?? []
  const topCardsTotal = topMain.length
  const topCardsPages = Math.ceil(Math.min(topCardsTotal, 100) / TOP_CARDS_PER_PAGE)
  const topCardsSlice = topMain.slice(topCardsPage * TOP_CARDS_PER_PAGE, (topCardsPage + 1) * TOP_CARDS_PER_PAGE)

  const setPreset = (preset: 'all' | '2weeks' | 'month' | 'lastEvent') => {
    const p = new URLSearchParams(searchParams)
    if (preset === 'all' || !maxDate) {
      setDateFrom(null)
      setDateTo(null)
      p.delete('date_from')
      p.delete('date_to')
    } else if (preset === 'lastEvent' && lastEventDate) {
      setDateFrom(lastEventDate)
      setDateTo(lastEventDate)
      p.set('date_from', lastEventDate)
      p.set('date_to', lastEventDate)
    } else {
      const to = maxDate
      const from = preset === '2weeks' ? dateMinusDays(maxDate, 14) : dateMinusDays(maxDate, 30)
      setDateTo(to)
      setDateFrom(from)
      p.set('date_from', from)
      p.set('date_to', to)
    }
    setSearchParams(p)
  }

  return (
    <div style={{ opacity: loading ? 0.6 : 1, transition: 'opacity 0.2s' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <h1 className="page-title" style={{ margin: 0 }}>
          Metagame Analysis{formatName && <span style={{ fontSize: '0.7em', color: 'var(--text-muted)', marginLeft: '0.5rem' }}>— {formatName}</span>}
        </h1>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center' }}>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Date range:</span>
            <button
              type="button"
              className="btn"
              style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }}
              onClick={() => setPreset('all')}
            >
              All time
            </button>
            <button
              type="button"
              className="btn"
              style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }}
              onClick={() => setPreset('month')}
            >
              Last month
            </button>
            <button
              type="button"
              className="btn"
              style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }}
              onClick={() => setPreset('2weeks')}
            >
              Last 2 weeks
            </button>
            <button
              type="button"
              className="btn"
              style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }}
              onClick={() => setPreset('lastEvent')}
            >
              Last event
            </button>
          </div>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginRight: '0.5rem' }}>Event:</label>
            <select
              value={eventId ?? ''}
              onChange={(e) => setEventFilter(e.target.value ? parseInt(e.target.value, 10) : null)}
              style={{ padding: '0.25rem 0.5rem' }}
            >
              <option value="">All events</option>
              {events.map((e) => (
                <option key={e.event_id} value={e.event_id}>
                  {e.event_name} ({e.date})
                </option>
              ))}
            </select>
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={placementWeighted}
              onChange={(e) => setPlacementWeighted(e.target.checked)}
            />
            Placement weighted
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={ignoreLands}
              onChange={(e) => setIgnoreLands(e.target.checked)}
            />
            Ignore lands
          </label>
        </div>
      </div>

      <div className="chart-container">
        <h3 style={{ margin: '0 0 1rem' }}>
          Commander Distribution
          {placementWeighted && <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginLeft: '0.5rem' }}>weighted by placement</span>}
        </h3>
        <ResponsiveContainer width="100%" height={400}>
          <BarChart data={commanders.slice(0, 15)} margin={{ top: 20, right: 30, left: 20, bottom: 80 }}
            style={{ cursor: 'pointer' }}
            onClick={(state) => {
              if (state?.activeLabel) navigate(`/decks?deck_name=${encodeURIComponent(state.activeLabel)}`)
            }}
          >
            <XAxis dataKey="commander" angle={-45} textAnchor="end" height={80} tick={{ fontSize: 11 }} />
            <YAxis />
            <Tooltip />
            <Bar dataKey="count" fill="#1d9bf0" name={placementWeighted ? 'Weighted Score' : 'Decks'} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="chart-container">
        <h3 style={{ margin: '0 0 1rem' }}>
          Archetype Distribution (Top 8)
          {placementWeighted && <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginLeft: '0.5rem' }}>weighted by placement</span>}
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <PieChart>
            <Pie
              data={archetypes.slice(0, 8)}
              dataKey="count"
              nameKey="archetype"
              cx="50%"
              cy="50%"
              outerRadius={100}
              label={({ archetype, pct }) => `${archetype} (${pct}%)`}
              style={{ cursor: 'pointer' }}
              onClick={(data) => {
                if (data?.archetype) navigate(`/decks?deck_name=${encodeURIComponent(data.archetype)}`)
              }}
            >
              {archetypes.slice(0, 8).map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip />
            <Legend onClick={(e) => {
              if (e?.value) navigate(`/decks?deck_name=${encodeURIComponent(String(e.value))}`)
            }} />
          </PieChart>
        </ResponsiveContainer>
      </div>

      <div className="chart-container">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
          <h3 style={{ margin: 0 }}>
            Top Cards (Mainboard)
            {placementWeighted && <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginLeft: '0.5rem' }}>sorted by weighted score</span>}
          </h3>
          {topCardsPages > 1 && (
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                {topCardsPage * TOP_CARDS_PER_PAGE + 1}–{Math.min((topCardsPage + 1) * TOP_CARDS_PER_PAGE, Math.min(topCardsTotal, 100))} of {Math.min(topCardsTotal, 100)}
              </span>
              <button
                type="button"
                className="btn"
                style={{ padding: '0.2rem 0.5rem', fontSize: '0.8rem' }}
                disabled={topCardsPage === 0}
                onClick={() => setTopCardsPage((p) => Math.max(0, p - 1))}
              >
                Prev
              </button>
              <button
                type="button"
                className="btn"
                style={{ padding: '0.2rem 0.5rem', fontSize: '0.8rem' }}
                disabled={topCardsPage >= topCardsPages - 1}
                onClick={() => setTopCardsPage((p) => Math.min(topCardsPages - 1, p + 1))}
              >
                Next
              </button>
            </div>
          )}
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Card</th>
                <th>Decks</th>
                <th>Play Rate</th>
                <th>{placementWeighted ? 'Weighted Score' : 'Copies'}</th>
              </tr>
            </thead>
            <tbody>
              {topCardsSlice.map((c, i) => (
                <tr key={c.card}>
                  <td style={{ color: 'var(--text-muted)' }}>{topCardsPage * TOP_CARDS_PER_PAGE + i + 1}</td>
                  <td>
                    <CardHover cardName={c.card} linkTo>{c.card}</CardHover>
                  </td>
                  <td>{c.decks}</td>
                  <td>{c.play_rate_pct}%</td>
                  <td>{c.total_copies}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
