import { useEffect, useState } from 'react'
import { useParams, useSearchParams, useNavigate, Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts'
import { getArchetypeDetail, getCardLookup, getDecks, getMatchupsSummary } from '../api'
import type { CardLookupResult } from '../api'
import type { ArchetypeDetail as ArchetypeDetailType, Deck } from '../types'
import ManaSymbols from '../components/ManaSymbols'
import Skeleton from '../components/Skeleton'
import TopCardsSection from '../components/TopCardsSection'
import { MTG_COLOR_FILL } from '../constants'
import { PieChartTooltipContent } from '../components/PieChartTooltip'
import { reportError } from '../utils'

const WUBRG_ORDER = ['W', 'U', 'B', 'R', 'G'] as const

export default function ArchetypeDetail() {
  const { archetypeName } = useParams<{ archetypeName: string }>()
  const [searchParams] = useSearchParams()
  const [detail, setDetail] = useState<ArchetypeDetailType | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [cardMeta, setCardMeta] = useState<Record<string, CardLookupResult>>({})
  const [loadingCardMeta, setLoadingCardMeta] = useState(false)
  const [topDecks, setTopDecks] = useState<Deck[]>([])
  const [ignoreLands, setIgnoreLands] = useState(false)
  const [matchupRows, setMatchupRows] = useState<Awaited<ReturnType<typeof getMatchupsSummary>>['list']>([])

  const navigate = useNavigate()
  const eventIdsParam = searchParams.get('event_ids') ?? undefined

  useEffect(() => {
    if (!archetypeName) return
    setLoading(true)
    setNotFound(false)
    getArchetypeDetail(decodeURIComponent(archetypeName), {
      eventIds: eventIdsParam ?? undefined,
      ignoreLands,
    })
      .then(setDetail)
      .catch((e) => {
        if (e.message?.toLowerCase().includes('not found') || e.message?.toLowerCase().includes('404')) {
          setNotFound(true)
          setDetail(null)
        } else {
          toast.error(reportError(e))
        }
      })
      .finally(() => setLoading(false))
  }, [archetypeName, eventIdsParam, ignoreLands])

  useEffect(() => {
    if (!archetypeName) return
    getMatchupsSummary({ archetype: [decodeURIComponent(archetypeName)] })
      .then((res) => setMatchupRows(res.list))
      .catch(() => setMatchupRows([]))
  }, [archetypeName])

  useEffect(() => {
    const topMain = detail?.top_cards_main ?? []
    if (topMain.length === 0) {
      setCardMeta({})
      return
    }
    setLoadingCardMeta(true)
    getCardLookup(topMain.map((c) => c.card))
      .then(setCardMeta)
      .catch(() => setCardMeta({}))
      .finally(() => setLoadingCardMeta(false))
  }, [detail?.top_cards_main])

  useEffect(() => {
    if (!detail?.archetype) {
      setTopDecks([])
      return
    }
    getDecks({
      archetype: detail.archetype,
      event_ids: eventIdsParam ?? undefined,
      sort: 'rank',
      order: 'asc',
      limit: 5,
    })
      .then((r) => setTopDecks(r.decks))
      .catch(() => setTopDecks([]))
  }, [detail?.archetype, eventIdsParam])

  if (!archetypeName) {
    return (
      <div className="chart-container">
        <p style={{ color: 'var(--text-muted)' }}>Missing archetype.</p>
        <Link to="/archetypes" style={{ color: 'var(--accent)' }}>Back to Archetypes</Link>
      </div>
    )
  }

  const displayName = decodeURIComponent(archetypeName)

  if (loading && !detail) {
    return (
      <div>
        <div style={{ marginBottom: '1rem' }}>
          <Skeleton width={320} height={32} />
          <Skeleton width={120} height={20} style={{ marginTop: '0.5rem' }} />
        </div>
        <div className="deck-analysis-grid">
          <Skeleton width="100%" height={200} />
          <Skeleton width="100%" height={200} />
          <Skeleton width="100%" height={200} />
        </div>
      </div>
    )
  }

  if (notFound || !detail) {
    return (
      <div className="chart-container" style={{ textAlign: 'center', padding: '2rem' }}>
        <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>
          Archetype &quot;{displayName}&quot; not found or no decks in the selected timeframe.
        </p>
        <Link to="/archetypes" className="btn" style={{ display: 'inline-block' }}>
          Back to Archetypes
        </Link>
      </div>
    )
  }

  const a = detail.average_analysis
  const hasCurve = a.mana_curve && Object.keys(a.mana_curve).length > 0
  const hasColor = a.color_distribution && Object.values(a.color_distribution).some((v) => v > 0)
  const hasLands = a.lands_distribution && (a.lands_distribution.lands > 0 || a.lands_distribution.nonlands > 0)
  const hasType = a.type_distribution && Object.keys(a.type_distribution).length > 0

  const topMain = detail.top_cards_main ?? []

  const archetypeManaCost = (() => {
    const dist = detail?.average_analysis?.color_distribution
    if (!dist) return ''
    const colors = WUBRG_ORDER.filter((c) => (dist[c] ?? 0) > 0)
    return colors.length ? `{${colors.join('}{')}}` : ''
  })()

  const matchupRowsFiltered = matchupRows.filter(
    (row) =>
      (row.opponent_archetype || '').trim().toLowerCase() !== (detail.archetype || '').trim().toLowerCase()
  )

  return (
    <div style={{ opacity: loading ? 0.6 : 1, transition: 'opacity 0.2s' }}>
      <button type="button" className="btn" style={{ marginBottom: '1rem' }} onClick={() => navigate(-1)}>
        Back
      </button>
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 className="page-title" style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          {detail.archetype}
          {archetypeManaCost ? <ManaSymbols manaCost={archetypeManaCost} size={28} /> : null}
        </h1>
        <p style={{ margin: '0.25rem 0 0', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
          Average of {detail.deck_count} deck{detail.deck_count !== 1 ? 's' : ''}
          {eventIdsParam && ' in selected events'}
          {detail.deck_count > 0 && detail.deck_count_top8 != null && (
            <>
              {' · '}
              <span title={`${detail.deck_count_top8} of ${detail.deck_count} decks made top 8`}>
                Conversion: {Math.round((detail.deck_count_top8 / detail.deck_count) * 1000) / 10}%
              </span>
            </>
          )}
        </p>
        <div style={{ marginTop: '0.5rem' }}>
          <Link
            to={`/decks?archetype=${encodeURIComponent(detail.archetype)}${eventIdsParam ? `&event_ids=${encodeURIComponent(eventIdsParam)}` : ''}`}
            style={{ fontSize: '0.875rem', color: 'var(--accent)' }}
          >
            View all decks for this archetype
          </Link>
        </div>
      </div>

      {topDecks.length > 0 && (
        <div className="chart-container" style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ margin: '0 0 0.75rem' }}>Top 5 decks</h3>
          <p style={{ margin: '0 0 0.75rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            Best ranked decks in this archetype (same timeframe).
          </p>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {topDecks.map((deck) => (
              <li key={deck.deck_id} style={{ marginBottom: '0.5rem' }}>
                <Link to={`/decks/${deck.deck_id}`} style={{ color: 'var(--accent)', fontWeight: 500 }}>
                  {deck.name}
                </Link>
                {' — '}
                <span style={{ color: 'var(--text-muted)' }}>
                  {deck.player} · {deck.event_name} · {deck.date}
                  {deck.rank && ` · #${deck.rank}`}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <h3 style={{ margin: '0 0 0.75rem' }}>Average deck composition</h3>
      <div className="deck-analysis-grid">
        {hasCurve && (
          <div className="chart-container">
            <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Mana Curve</h4>
            <ResponsiveContainer width="100%" height={180}>
              <ComposedChart
                data={(() => {
                  const curve = a.mana_curve || {}
                  const perm = a.mana_curve_permanent ?? {}
                  const nonPerm = a.mana_curve_non_permanent ?? {}
                  const hasSplit = Object.keys(perm).length > 0 || Object.keys(nonPerm).length > 0
                  const maxCmc = Math.max(0, ...Object.keys(curve).map(Number), ...Object.keys(perm).map(Number), ...Object.keys(nonPerm).map(Number))
                  return Array.from({ length: maxCmc + 1 }, (_, cmc) => {
                    const p = hasSplit ? (perm[String(cmc)] ?? 0) : (curve[String(cmc)] ?? 0)
                    const n = hasSplit ? (nonPerm[String(cmc)] ?? 0) : 0
                    return { cmc, permanent: p, non_permanent: n, count: p + n }
                  })
                })()}
                margin={{ top: 10, right: 16, left: 36, bottom: 24 }}
              >
                <XAxis dataKey="cmc" />
                <YAxis width={28} />
                <Tooltip
                  contentStyle={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border)',
                    borderRadius: 8,
                    color: 'var(--text)',
                  }}
                  labelStyle={{ color: 'var(--text)', fontWeight: 600 }}
                />
                <Bar dataKey="permanent" stackId="curve" fill="#22c55e" name="Permanents (avg)" />
                <Bar dataKey="non_permanent" stackId="curve" fill="#ef4444" name="Non-permanents (avg)" />
                <Line type="monotone" dataKey="count" stroke="#c2410c" strokeWidth={2} dot={{ r: 4, fill: '#c2410c' }} name="" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
        {hasColor && (
          <div className="chart-container">
            <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Color Distribution</h4>
            <ResponsiveContainer width="100%" height={200}>
              <PieChart margin={{ top: 8, right: 8, bottom: 58, left: 8 }}>
                <Pie
                  data={[
                    { name: 'White', value: a.color_distribution.W || 0, color: MTG_COLOR_FILL.White },
                    { name: 'Blue', value: a.color_distribution.U || 0, color: MTG_COLOR_FILL.Blue },
                    { name: 'Black', value: a.color_distribution.B || 0, color: MTG_COLOR_FILL.Black },
                    { name: 'Red', value: a.color_distribution.R || 0, color: MTG_COLOR_FILL.Red },
                    { name: 'Green', value: a.color_distribution.G || 0, color: MTG_COLOR_FILL.Green },
                    { name: 'Colorless', value: a.color_distribution.C || 0, color: MTG_COLOR_FILL.Colorless },
                  ].filter((d) => d.value > 0)}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={58}
                >
                  {[
                    { name: 'White', value: a.color_distribution.W || 0, color: MTG_COLOR_FILL.White },
                    { name: 'Blue', value: a.color_distribution.U || 0, color: MTG_COLOR_FILL.Blue },
                    { name: 'Black', value: a.color_distribution.B || 0, color: MTG_COLOR_FILL.Black },
                    { name: 'Red', value: a.color_distribution.R || 0, color: MTG_COLOR_FILL.Red },
                    { name: 'Green', value: a.color_distribution.G || 0, color: MTG_COLOR_FILL.Green },
                    { name: 'Colorless', value: a.color_distribution.C || 0, color: MTG_COLOR_FILL.Colorless },
                  ]
                    .filter((d) => d.value > 0)
                    .map((d) => (
                      <Cell key={d.name} fill={d.color} />
                    ))}
                </Pie>
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null
                    const p = payload[0]?.payload as { name?: string; value?: number }
                    if (!p) return null
                    return (
                      <PieChartTooltipContent
                        title={p.name ?? ''}
                        subtitle={p.value != null ? `${p.value}%` : undefined}
                      />
                    )
                  }}
                />
                <Legend layout="horizontal" verticalAlign="bottom" wrapperStyle={{ paddingTop: 4 }} formatter={(_, entry: { payload?: { name?: string; value?: number } }) => entry?.payload ? `${entry.payload.name ?? ''} ${entry.payload.value ?? ''}%` : ''} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
        {hasLands && (
          <div className="chart-container">
            <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Lands Distribution</h4>
            <ResponsiveContainer width="100%" height={200}>
              <PieChart margin={{ top: 8, right: 8, bottom: 58, left: 8 }}>
                <Pie
                  data={[
                    { name: 'Lands', value: a.lands_distribution.lands, color: '#8b7355' },
                    { name: 'Non-Lands', value: a.lands_distribution.nonlands, color: '#1d9bf0' },
                  ].filter((d) => d.value > 0)}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={58}
                >
                  {[
                    { name: 'Lands', value: a.lands_distribution.lands, color: '#8b7355' },
                    { name: 'Non-Lands', value: a.lands_distribution.nonlands, color: '#1d9bf0' },
                  ]
                    .filter((d) => d.value > 0)
                    .map((d) => (
                      <Cell key={d.name} fill={d.color} />
                    ))}
                </Pie>
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null
                    const p = payload[0]?.payload as { name?: string; value?: number }
                    if (!p) return null
                    const total = a.lands_distribution.lands + a.lands_distribution.nonlands
                    const pct = total ? Math.round((100 * (p.value ?? 0)) / total) : 0
                    return (
                      <PieChartTooltipContent
                        title={p.name ?? ''}
                        subtitle={`${p.value?.toFixed(1) ?? ''} (${pct}%)`}
                      />
                    )
                  }}
                />
                <Legend
                  layout="horizontal"
                  verticalAlign="bottom"
                  formatter={(_, entry: { payload?: { name?: string; value?: number } }) => {
                    const p = entry?.payload
                    if (!p) return ''
                    const total = a.lands_distribution.lands + a.lands_distribution.nonlands
                    const pct = total ? Math.round((100 * (p.value ?? 0)) / total) : 0
                    return `${p.name ?? ''} ${p.value?.toFixed(1) ?? ''} (${pct}%)`
                  }}
                  wrapperStyle={{ paddingTop: 4 }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
        {hasType && (
          <div className="chart-container">
            <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Card Type Distribution</h4>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart margin={{ top: 28, right: 8, bottom: 72, left: 8 }}>
                <Pie
                  data={Object.entries(a.type_distribution)
                    .filter(([, v]) => v > 0)
                    .map(([name, value], i) => ({
                      name,
                      value,
                      color: ['#1d9bf0', '#00ba7c', '#f7931a', '#e91e63', '#9c27b0', '#8b7355', '#00bcd4'][i % 7],
                    }))}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={54}
                >
                  {Object.entries(a.type_distribution)
                    .filter(([, v]) => v > 0)
                    .map(([name], i) => (
                      <Cell
                        key={name}
                        fill={['#1d9bf0', '#00ba7c', '#f7931a', '#e91e63', '#9c27b0', '#8b7355', '#00bcd4'][i % 7]}
                      />
                    ))}
                </Pie>
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null
                    const p = payload[0]?.payload as { name?: string; value?: number }
                    if (!p) return null
                    return (
                      <PieChartTooltipContent
                        title={p.name ?? ''}
                        subtitle={p.value != null ? `${p.value}` : undefined}
                      />
                    )
                  }}
                />
                <Legend layout="horizontal" verticalAlign="bottom" wrapperStyle={{ paddingTop: 4 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      <div style={{ marginTop: '1.5rem' }}>
        <TopCardsSection
          title="Most played cards"
          topCardsMain={topMain}
          cardMeta={cardMeta}
          loadingCardMeta={loadingCardMeta}
          extraToolbar={
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.875rem' }}>
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
      </div>

      {matchupRowsFiltered.length > 0 && (
        <div style={{ marginTop: '1.5rem' }}>
          <h3 style={{ margin: '0 0 0.75rem' }}>Matchup performance</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '0.5rem' }}>
            From event feedback. Same-archetype matchups excluded. <Link to="/matchups">View full matchups</Link>
          </p>
          <div className="table-wrap-outer">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Opponent archetype</th>
                    <th scope="col">Record</th>
                    <th scope="col">Win rate</th>
                    <th scope="col">Matches</th>
                  </tr>
                </thead>
                <tbody>
                  {matchupRowsFiltered.map((row, i) => (
                    <tr key={i}>
                      <td>{row.opponent_archetype}</td>
                      <td>{row.wins}–{row.losses}–{row.draws}</td>
                      <td>{(row.win_rate * 100).toFixed(1)}%</td>
                      <td>{row.matches}</td>
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
