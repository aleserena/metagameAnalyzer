import { useEffect, useState } from 'react'
import { useSearchParams, useNavigate, Link } from 'react-router-dom'
import toast from 'react-hot-toast'
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
import { getMetagame, getFormatInfo, getCardLookup } from '../api'
import type { CardLookupResult } from '../api'
import CardHover from '../components/CardHover'
import EmptyState from '../components/EmptyState'
import EventSelector from '../components/EventSelector'
import Skeleton from '../components/Skeleton'
import TopCardsSection from '../components/TopCardsSection'
import { reportError } from '../utils'
import type { MetagameReport } from '../types'
import { useEventMetadata } from '../hooks/useEventMetadata'
import { MTG_COLOR_FILL } from '../constants'
import { PIE_TOOLTIP_STYLE, PieChartTooltipContent } from '../components/PieChartTooltip'

const COLORS = ['#1d9bf0', '#00ba7c', '#f7931a', '#e91e63', '#9c27b0', '#00bcd4', '#ff9800', '#4caf50']

export default function Metagame() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [metagame, setMetagame] = useState<MetagameReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [placementWeighted, setPlacementWeighted] = useState(false)
  const [ignoreLands, setIgnoreLands] = useState(false)
  const [top8Only, setTop8Only] = useState(false)
  const [eventIds, setEventIds] = useState<(number | string)[]>(() => {
    const param = searchParams.get('event_ids') ?? searchParams.get('event_id')
    if (!param) return []
    return param.split(',').map((s) => s.trim()).filter(Boolean)
  })
  const [cardMeta, setCardMeta] = useState<Record<string, CardLookupResult>>({})
  const [loadingCardMeta, setLoadingCardMeta] = useState(false)
  const { events, maxDate, lastEventDate, error: eventMetadataError } = useEventMetadata()
  const [formatName, setFormatName] = useState<string | null>(null)

  useEffect(() => {
    const param = searchParams.get('event_ids') ?? searchParams.get('event_id')
    if (!param) setEventIds([])
    else setEventIds(param.split(',').map((s) => s.trim()).filter(Boolean))
  }, [searchParams])

  useEffect(() => {
    if (eventMetadataError) toast.error(reportError(new Error(eventMetadataError)))
  }, [eventMetadataError])

  useEffect(() => {
    getFormatInfo().then((r) => setFormatName(r.format_name))
  }, [])

  useEffect(() => {
    setLoading(true)
    setError(null)
    const eventIdsParam = eventIds.length ? eventIds.map(String).join(',') : undefined
    getMetagame(placementWeighted, ignoreLands, undefined, undefined, undefined, eventIdsParam, top8Only)
      .then((data) => {
        setMetagame(data)
        setError(null)
      })
      .catch((e) => {
        setError(e.message)
        toast.error(reportError(e))
      })
      .finally(() => setLoading(false))
  }, [placementWeighted, ignoreLands, top8Only, eventIds])

  useEffect(() => {
    const topMain = metagame?.top_cards_main ?? []
    if (topMain.length === 0) {
      setCardMeta({})
      return
    }
    setLoadingCardMeta(true)
    getCardLookup(topMain.map((c) => c.card))
      .then(setCardMeta)
      .finally(() => setLoadingCardMeta(false))
  }, [metagame?.top_cards_main])

  const setEventFilter = (ids: (number | string)[]) => {
    setEventIds(ids)
    const p = new URLSearchParams(searchParams)
    if (ids.length) p.set('event_ids', ids.map(String).join(','))
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
  if (error) {
    return (
      <div>
        <h1 className="page-title" style={{ margin: 0 }}>Metagame Analysis</h1>
        <div className="chart-container" style={{ textAlign: 'center', padding: '2rem', marginTop: '1.5rem' }}>
          <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>{error}</p>
          <button
            type="button"
            className="btn"
            onClick={() => {
              setError(null)
              setLoading(true)
              const eventIdsParam = eventIds.length ? eventIds.map(String).join(',') : undefined
              getMetagame(placementWeighted, ignoreLands, undefined, undefined, undefined, eventIdsParam, top8Only)
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

  const summary = metagame?.summary ?? { total_decks: 0 }
  if (summary.total_decks === 0) {
    return (
      <EmptyState
        title="No metagame data"
        description="Load or scrape deck data to analyze the metagame."
        action={<Link to="/scrape" className="btn" style={{ textDecoration: 'none' }}>Load or scrape data</Link>}
      />
    )
  }

  const commanders = metagame?.commander_distribution ?? []
  const archetypes = metagame?.archetype_distribution ?? []
  const colorDistribution = metagame?.color_distribution ?? []
  const colorCountDistribution = metagame?.color_count_distribution ?? []
  const topMain = metagame?.top_cards_main ?? []

  return (
    <div style={{ opacity: loading ? 0.6 : 1, transition: 'opacity 0.2s' }}>
      <div className="toolbar toolbar--stack-on-mobile" style={{ marginBottom: '1.5rem', gap: '0.75rem', justifyContent: 'space-between' }}>
        <h1 className="page-title" style={{ margin: 0 }}>
          Metagame Analysis{formatName && <span style={{ fontSize: '0.7em', color: 'var(--text-muted)', marginLeft: '0.5rem' }}>— {formatName}</span>}
        </h1>
        <div
          className="metagame-event-selector-wrap"
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
            onChange={setEventFilter}
            showDatePresets
            maxDate={maxDate}
            lastEventDate={lastEventDate}
          />
        </div>
      </div>

      <div className="chart-container">
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
          <h3 style={{ margin: 0 }}>Commander Distribution</h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.875rem' }}>
            <span style={{ color: 'var(--text-muted)' }}>Data:</span>
            <button
              type="button"
              className="btn"
              style={{
                padding: '0.25rem 0.5rem',
                fontSize: '0.8125rem',
                background: !top8Only ? 'var(--accent)' : 'transparent',
                color: !top8Only ? 'var(--bg)' : 'var(--text)',
                border: '1px solid var(--border)',
              }}
              onClick={() => setTop8Only(false)}
              aria-pressed={!top8Only}
            >
              All decks
            </button>
            <button
              type="button"
              className="btn"
              style={{
                padding: '0.25rem 0.5rem',
                fontSize: '0.8125rem',
                background: top8Only ? 'var(--accent)' : 'transparent',
                color: top8Only ? 'var(--bg)' : 'var(--text)',
                border: '1px solid var(--border)',
              }}
              onClick={() => setTop8Only(true)}
              aria-pressed={top8Only}
            >
              Top 8 only
            </button>
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.875rem' }}>
            <input
              type="checkbox"
              checked={placementWeighted}
              onChange={(e) => setPlacementWeighted(e.target.checked)}
              aria-label="Placement weighted"
            />
            Placement weighted
          </label>
          {placementWeighted && <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>weighted by placement</span>}
        </div>
        <ResponsiveContainer width="100%" height={400}>
          <BarChart data={commanders.slice(0, 15)} margin={{ top: 15, right: 25, left: 35, bottom: 90 }}
            style={{ cursor: 'pointer' }}
            onClick={(state) => {
              if (state?.activeLabel) navigate(`/decks?archetype=${encodeURIComponent(state.activeLabel)}`)
            }}
          >
            <XAxis dataKey="commander" angle={-45} textAnchor="end" height={80} tick={{ fontSize: 11 }} />
            <YAxis width={32} />
            <Tooltip
              contentStyle={{
                background: 'var(--bg-card)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                color: 'var(--text)',
              }}
              labelStyle={{ color: 'var(--text)', fontWeight: 600 }}
            />
            <Bar dataKey="count" fill="#1d9bf0" name={placementWeighted ? 'Weighted Score' : 'Decks'} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="chart-container">
        <h3 style={{ margin: '0 0 1rem' }}>Most Played Colors</h3>
        <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', margin: '0 0 1rem' }}>Deck color identity from commanders</p>
        {colorDistribution.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <PieChart margin={{ top: 15, right: 15, bottom: 60, left: 15 }}>
              <Pie
                data={colorDistribution}
                dataKey="count"
                nameKey="color"
                cx="50%"
                cy="50%"
                outerRadius={90}
                label={({ color, pct }) => `${color} (${pct}%)`}
              >
                {colorDistribution.map((entry) => (
                  <Cell key={entry.color} fill={MTG_COLOR_FILL[entry.color] ?? COLORS[0]} />
                ))}
              </Pie>
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const p = payload[0]?.payload as { color: string; count: number; pct: number; top_decks?: { name: string; count: number }[] }
                  if (!p) return null
                  const topDecks = p.top_decks ?? []
                  return (
                    <div style={{ ...PIE_TOOLTIP_STYLE, minWidth: 180 }}>
                      <div style={{ fontWeight: 600, marginBottom: '0.35rem', color: 'var(--text)' }}>
                        {p.color}
                      </div>
                      <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: topDecks.length ? '0.5rem' : 0 }}>
                        {p.count} deck{p.count === 1 ? '' : 's'} ({p.pct}%)
                      </div>
                      {topDecks.length > 0 && (
                        <div style={{ fontSize: '0.8125rem', color: 'var(--text)', borderTop: '1px solid var(--border)', paddingTop: '0.5rem', marginTop: '0.25rem' }}>
                          <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>Top decks</div>
                          <ul style={{ margin: 0, paddingLeft: '1.1rem', listStyle: 'disc' }}>
                            {topDecks.slice(0, 5).map((d) => (
                              <li key={d.name} style={{ marginBottom: '0.15rem' }}>
                                {d.name} — {d.count}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )
                }}
              />
              <Legend formatter={(value, entry: unknown) => {
                const p = entry && typeof entry === 'object' && 'payload' in entry ? (entry as { payload?: { color?: string; pct?: number } }).payload : undefined
                return p?.pct != null ? `${p.color ?? value} (${p.pct}%)` : value
              }} />
            </PieChart>
          </ResponsiveContainer>
        ) : (
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>No color data (no commanders or lookup unavailable)</p>
        )}
      </div>

      <div className="chart-container">
        <h3 style={{ margin: '0 0 1rem' }}>
          Archetype Distribution (8 more played decks)
          {placementWeighted && <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginLeft: '0.5rem' }}>weighted by placement</span>}
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <PieChart margin={{ top: 15, right: 15, bottom: 60, left: 15 }}>
            <Pie
              data={archetypes.slice(0, 8)}
              dataKey="count"
              nameKey="archetype"
              cx="50%"
              cy="50%"
              outerRadius={90}
              style={{ cursor: 'pointer' }}
              onClick={(data) => {
                if (data?.archetype) navigate(`/decks?archetype=${encodeURIComponent(data.archetype)}`)
              }}
            >
              {archetypes.slice(0, 8).map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const p = payload[0]?.payload as { archetype: string; count: number; pct?: number }
                if (!p) return null
                return (
                  <PieChartTooltipContent
                    title={p.archetype}
                    subtitle={`${p.count} deck${p.count === 1 ? '' : 's'} (${p.pct ?? 0}%)`}
                  />
                )
              }}
            />
            <Legend layout="horizontal" verticalAlign="bottom" onClick={(e) => {
              if (e?.value) navigate(`/decks?archetype=${encodeURIComponent(String(e.value))}`)
            }} formatter={(value, entry: unknown) => {
              const p = entry && typeof entry === 'object' && 'payload' in entry ? (entry as { payload?: { archetype?: string; pct?: number } }).payload : undefined
              return p?.pct != null ? `${p.archetype ?? ''} (${p.pct}%)` : value
            }} />
          </PieChart>
        </ResponsiveContainer>
      </div>

      <div className="chart-container">
        <h3 style={{ margin: '0 0 1rem' }}>Metagame by Number of Colors</h3>
        <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', margin: '0 0 1rem' }}>Share of decks that are monocolor, 2-color, 3-color, etc.</p>
        {colorCountDistribution.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <PieChart margin={{ top: 15, right: 15, bottom: 60, left: 15 }}>
              <Pie
                data={colorCountDistribution}
                dataKey="count"
                nameKey="label"
                cx="50%"
                cy="50%"
                outerRadius={90}
                label={({ label, pct }) => `${label} (${pct}%)`}
              >
                {colorCountDistribution.map((entry, i) => (
                  <Cell key={entry.label} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const p = payload[0]?.payload as { label: string; count: number; pct: number; top_decks?: { name: string; count: number }[] }
                  if (!p) return null
                  const topDecks = p.top_decks ?? []
                  return (
                    <div style={{ ...PIE_TOOLTIP_STYLE, minWidth: 180 }}>
                      <div style={{ fontWeight: 600, marginBottom: '0.35rem', color: 'var(--text)' }}>{p.label}</div>
                      <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: topDecks.length ? '0.5rem' : 0 }}>
                        {p.count} deck{p.count === 1 ? '' : 's'} ({p.pct}%)
                      </div>
                      {topDecks.length > 0 && (
                        <div style={{ fontSize: '0.8125rem', color: 'var(--text)', borderTop: '1px solid var(--border)', paddingTop: '0.5rem', marginTop: '0.25rem' }}>
                          <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>Top decks</div>
                          <ul style={{ margin: 0, paddingLeft: '1.1rem', listStyle: 'disc' }}>
                            {topDecks.slice(0, 5).map((d) => (
                              <li key={d.name} style={{ marginBottom: '0.15rem' }}>
                                {d.name} — {d.count}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )
                }}
              />
              <Legend formatter={(value, entry: unknown) => {
                const p = entry && typeof entry === 'object' && 'payload' in entry ? (entry as { payload?: { label?: string; pct?: number } }).payload : undefined
                return p?.pct != null ? `${p.label ?? value} (${p.pct}%)` : value
              }} />
            </PieChart>
          </ResponsiveContainer>
        ) : (
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>No data (no commanders or lookup unavailable)</p>
        )}
      </div>

      <TopCardsSection
        title="Top Cards (Mainboard)"
        subtitle={
          placementWeighted ? (
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginLeft: '0.5rem' }}>
              sorted by weighted score
            </span>
          ) : undefined
        }
        topCardsMain={topMain}
        cardMeta={cardMeta}
        loadingCardMeta={loadingCardMeta}
        placementWeighted={placementWeighted}
        extraToolbar={
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={ignoreLands}
              onChange={(e) => setIgnoreLands(e.target.checked)}
              aria-label="Ignore lands"
            />
            Ignore lands
          </label>
        }
      />

      {metagame?.card_synergy && metagame.card_synergy.length > 0 && (
        <div className="chart-container" style={{ marginTop: '1.5rem' }}>
          <h3 style={{ margin: '0 0 1rem' }}>Cards Often Played Together</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '1rem' }}>
            Pairs that appear in the same deck frequently (co-occurrence)
          </p>
          <div className="table-wrap-outer">
            <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Card A</th>
                  <th scope="col">Card B</th>
                  <th scope="col">Decks</th>
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
        </div>
      )}
    </div>
  )
}
