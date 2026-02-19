import { useEffect, useState } from 'react'
import { useSearchParams, useNavigate, Link } from 'react-router-dom'
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
import EventSelector from '../components/EventSelector'
import Skeleton from '../components/Skeleton'
import type { MetagameReport, Event } from '../types'

const COLORS = ['#1d9bf0', '#00ba7c', '#f7931a', '#e91e63', '#9c27b0', '#00bcd4', '#ff9800', '#4caf50']

export default function Metagame() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [metagame, setMetagame] = useState<MetagameReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [placementWeighted, setPlacementWeighted] = useState(false)
  const [ignoreLands, setIgnoreLands] = useState(false)
  const [eventIds, setEventIds] = useState<number[]>(() => {
    const param = searchParams.get('event_ids') ?? searchParams.get('event_id')
    if (!param) return []
    return param.split(',').map((s) => parseInt(s.trim(), 10)).filter((n) => !isNaN(n))
  })
  const [topCardsPage, setTopCardsPage] = useState(0)
  const [maxDate, setMaxDate] = useState<string | null>(null)
  const [lastEventDate, setLastEventDate] = useState<string | null>(null)
  const [formatName, setFormatName] = useState<string | null>(null)
  const [events, setEvents] = useState<Event[]>([])

  useEffect(() => {
    const param = searchParams.get('event_ids') ?? searchParams.get('event_id')
    if (!param) setEventIds([])
    else setEventIds(param.split(',').map((s) => parseInt(s.trim(), 10)).filter((n) => !isNaN(n)))
  }, [searchParams])

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
    const eventIdsParam = eventIds.length ? eventIds.join(',') : undefined
    getMetagame(placementWeighted, ignoreLands, undefined, undefined, undefined, eventIdsParam)
      .then(setMetagame)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [placementWeighted, ignoreLands, eventIds])

  const setEventFilter = (ids: number[]) => {
    setEventIds(ids)
    const p = new URLSearchParams(searchParams)
    if (ids.length) p.set('event_ids', ids.join(','))
    else {
      p.delete('event_ids')
      p.delete('event_id')
    }
    setSearchParams(p)
  }

  if (!metagame && loading) {
    return (
      <div>
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
          <Skeleton width={100} height={32} />
          <Skeleton width={120} height={32} />
          <Skeleton width={140} height={32} />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
          <div className="chart-container">
            <Skeleton width={200} height={24} style={{ marginBottom: '1rem' }} />
            <Skeleton width="100%" height={300} />
          </div>
          <div className="chart-container">
            <Skeleton width={200} height={24} style={{ marginBottom: '1rem' }} />
            <Skeleton width="100%" height={300} />
          </div>
        </div>
      </div>
    )
  }
  if (error) return <div className="error">{error}</div>

  const summary = metagame?.summary ?? { total_decks: 0 }
  if (summary.total_decks === 0) {
    return (
      <div className="chart-container" style={{ textAlign: 'center', padding: '3rem 2rem', maxWidth: 480, margin: '0 auto' }}>
        <p style={{ color: 'var(--text-muted)', marginBottom: '1rem', fontSize: '1.1rem' }}>No metagame data</p>
        <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
          Load or scrape deck data to analyze the metagame.
        </p>
        <Link to="/scrape" className="btn" style={{ textDecoration: 'none' }}>Load or scrape data</Link>
      </div>
    )
  }

  const TOP_CARDS_PER_PAGE = 50

  const commanders = metagame?.commander_distribution ?? []
  const archetypes = metagame?.archetype_distribution ?? []
  const topMain = metagame?.top_cards_main ?? []
  const topCardsTotal = topMain.length
  const topCardsPages = Math.ceil(Math.min(topCardsTotal, 100) / TOP_CARDS_PER_PAGE)
  const topCardsSlice = topMain.slice(topCardsPage * TOP_CARDS_PER_PAGE, (topCardsPage + 1) * TOP_CARDS_PER_PAGE)

  return (
    <div style={{ opacity: loading ? 0.6 : 1, transition: 'opacity 0.2s' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <h1 className="page-title" style={{ margin: 0 }}>
          Metagame Analysis{formatName && <span style={{ fontSize: '0.7em', color: 'var(--text-muted)', marginLeft: '0.5rem' }}>— {formatName}</span>}
        </h1>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'flex-end' }}>
          <EventSelector
            events={events}
            selectedIds={eventIds}
            onChange={setEventFilter}
            showDatePresets
            maxDate={maxDate}
            lastEventDate={lastEventDate}
          />
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
                if (data?.archetype) navigate(`/decks?archetype=${encodeURIComponent(data.archetype)}`)
              }}
            >
              {archetypes.slice(0, 8).map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip />
            <Legend onClick={(e) => {
              if (e?.value) navigate(`/decks?archetype=${encodeURIComponent(String(e.value))}`)
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

      {metagame?.card_synergy && metagame.card_synergy.length > 0 && (
        <div className="chart-container" style={{ marginTop: '1.5rem' }}>
          <h3 style={{ margin: '0 0 1rem' }}>Cards Often Played Together</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '1rem' }}>
            Pairs that appear in the same deck frequently (co-occurrence)
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Card A</th>
                  <th>Card B</th>
                  <th>Decks</th>
                </tr>
              </thead>
              <tbody>
                {metagame.card_synergy.map((s, i) => (
                  <tr key={`${s.card_a}-${s.card_b}-${i}`}>
                    <td>
                      <CardHover cardName={s.card_a} linkTo>{s.card_a}</CardHover>
                    </td>
                    <td>
                      <CardHover cardName={s.card_b} linkTo>{s.card_b}</CardHover>
                    </td>
                    <td>{s.decks}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
