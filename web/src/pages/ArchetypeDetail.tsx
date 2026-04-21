import { useEffect, useState } from 'react'
import { useParams, useSearchParams, useNavigate, Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import {
  ComposedChart,
  Bar,
  BarChart,
  Line,
  LineChart,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts'
import {
  getArchetypeDetail,
  getArchetypeCardTrends,
  getArchetypeWeeklyStats,
  getCardLookup,
  getDecks,
  getMatchupsSummary,
} from '../api'
import type {
  ArchetypeCardTrends,
  CardLookupResult,
  RecencyMode,
} from '../api'
import CardHover from '../components/CardHover'
import type { ArchetypeDetail as ArchetypeDetailType, ArchetypeWeeklyStats, Deck, TypicalListEntry } from '../types'
import ManaSymbols from '../components/ManaSymbols'
import Skeleton from '../components/Skeleton'
import TopCardsSection from '../components/TopCardsSection'
import { MTG_COLOR_FILL } from '../constants'
import { PieChartTooltipContent } from '../components/PieChartTooltip'
import { reportError } from '../utils'

const WUBRG_ORDER = ['W', 'U', 'B', 'R', 'G'] as const

type MatchupSortKey = 'opponent_archetype' | 'record' | 'win_rate' | 'matches'

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
  const [matchupSortBy, setMatchupSortBy] = useState<MatchupSortKey>('matches')
  const [matchupSortDesc, setMatchupSortDesc] = useState(true)
  const [recencyMode, setRecencyMode] = useState<RecencyMode>('events')
  const [recencyValue, setRecencyValue] = useState<number>(3)
  const [customRecentFrom, setCustomRecentFrom] = useState<string>('')
  const [trends, setTrends] = useState<ArchetypeCardTrends | null>(null)
  const [loadingTrends, setLoadingTrends] = useState(false)
  const [trendsError, setTrendsError] = useState<string | null>(null)
  const [weekly, setWeekly] = useState<ArchetypeWeeklyStats | null>(null)
  const [bucketOpen, setBucketOpen] = useState<{ core: boolean; staple: boolean; flex: boolean; tech: boolean }>({
    core: true,
    staple: true,
    flex: false,
    tech: false,
  })

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
    if (!archetypeName) return
    let cancelled = false
    getArchetypeWeeklyStats(decodeURIComponent(archetypeName), {
      eventIds: eventIdsParam ?? undefined,
    })
      .then((w) => { if (!cancelled) setWeekly(w) })
      .catch(() => { if (!cancelled) setWeekly(null) })
    return () => { cancelled = true }
  }, [archetypeName, eventIdsParam])

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

  useEffect(() => {
    if (!archetypeName) return
    if (recencyMode === 'custom' && !customRecentFrom) {
      setTrends(null)
      setTrendsError(null)
      return
    }
    let cancelled = false
    setLoadingTrends(true)
    setTrendsError(null)
    const handle = window.setTimeout(() => {
      getArchetypeCardTrends(decodeURIComponent(archetypeName), {
        eventIds: eventIdsParam ?? undefined,
        ignoreLands,
        recencyMode,
        recencyValue,
        recentFrom: recencyMode === 'custom' ? customRecentFrom : undefined,
      })
        .then((t) => {
          if (!cancelled) setTrends(t)
        })
        .catch((e) => {
          if (!cancelled) {
            setTrends(null)
            setTrendsError(e?.message || 'Failed to load trends')
          }
        })
        .finally(() => {
          if (!cancelled) setLoadingTrends(false)
        })
    }, recencyMode === 'custom' ? 300 : 0)
    return () => {
      cancelled = true
      window.clearTimeout(handle)
    }
  }, [archetypeName, eventIdsParam, ignoreLands, recencyMode, recencyValue, customRecentFrom])

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

  const handleMatchupSort = (key: MatchupSortKey) => {
    if (matchupSortBy === key) setMatchupSortDesc((d) => !d)
    else {
      setMatchupSortBy(key)
      setMatchupSortDesc(true)
    }
  }

  const matchupRowsSorted = [...matchupRowsFiltered].sort((a, b) => {
    let cmp = 0
    if (matchupSortBy === 'opponent_archetype') {
      cmp = (a.opponent_archetype || '').localeCompare(b.opponent_archetype || '')
    } else if (matchupSortBy === 'record' || matchupSortBy === 'matches') {
      const av = (a.wins ?? 0) + (a.losses ?? 0) + (a.draws ?? 0)
      const bv = (b.wins ?? 0) + (b.losses ?? 0) + (b.draws ?? 0)
      cmp = av - bv
    } else if (matchupSortBy === 'win_rate') {
      cmp = (a.win_rate ?? 0) - (b.win_rate ?? 0)
    }
    if (cmp === 0) {
      // stable tiebreakers: win_rate desc, then opponent name asc
      const wr = (a.win_rate ?? 0) - (b.win_rate ?? 0)
      if (wr !== 0) return matchupSortDesc ? -wr : wr
      return (a.opponent_archetype || '').localeCompare(b.opponent_archetype || '')
    }
    return matchupSortDesc ? -cmp : cmp
  })

  const matchupSortArrow = (key: MatchupSortKey) =>
    matchupSortBy === key ? (matchupSortDesc ? ' \u25BC' : ' \u25B2') : ''
  const matchupAriaSort = (key: MatchupSortKey): 'ascending' | 'descending' | 'none' =>
    matchupSortBy === key ? (matchupSortDesc ? 'descending' : 'ascending') : 'none'

  const MATCHUP_MIN_MATCHES = 5
  const matchupHeatRows = matchupRowsFiltered.filter((r) => (r.matches ?? 0) >= MATCHUP_MIN_MATCHES)
  const bestMatchups = [...matchupHeatRows]
    .sort((x, y) => (y.win_rate ?? 0) - (x.win_rate ?? 0))
    .slice(0, 3)
  const worstMatchups = [...matchupHeatRows]
    .sort((x, y) => (x.win_rate ?? 0) - (y.win_rate ?? 0))
    .slice(0, 3)

  const typicalList = detail.typical_list
  const topPlayers = detail.top_players ?? []
  const manaPips = a.mana_pips_by_color ?? {}
  const manaPipsData = (['W', 'U', 'B', 'R', 'G', 'C'] as const)
    .map((c) => ({
      color: c,
      label: ({ W: 'White', U: 'Blue', B: 'Black', R: 'Red', G: 'Green', C: 'Colorless' } as const)[c],
      pips: manaPips[c] ?? 0,
      fill: ({ W: MTG_COLOR_FILL.White, U: MTG_COLOR_FILL.Blue, B: MTG_COLOR_FILL.Black, R: MTG_COLOR_FILL.Red, G: MTG_COLOR_FILL.Green, C: MTG_COLOR_FILL.Colorless } as Record<string, string>)[c],
    }))
    .filter((d) => d.pips > 0)
  const hasManaPips = manaPipsData.length > 0

  const weeks = weekly?.weeks ?? []
  const hasWeekly = weeks.length >= 2

  const bucketMeta: { key: keyof NonNullable<typeof typicalList>; title: string; desc: string; color: string }[] = [
    { key: 'core', title: 'Core', desc: '≥80% play rate & typically 3+ copies', color: '#22c55e' },
    { key: 'staple', title: 'Staple', desc: '50–80% play rate', color: '#1d9bf0' },
    { key: 'flex', title: 'Flex', desc: '20–50% play rate', color: '#f59e0b' },
    { key: 'tech', title: 'Tech', desc: '5–20% play rate', color: '#9c27b0' },
  ]

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

      {hasWeekly && (
        <div className="chart-container" style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ margin: '0 0 0.5rem' }}>Popularity & top-8 rate over time</h3>
          <p style={{ margin: '0 0 0.75rem', fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
            One point per ISO week. Share = decks of this archetype ÷ all decks in that week. Top-8 rate = top-8 finishes ÷ decks of this archetype that week.
          </p>
          <div className="deck-analysis-grid">
            <div>
              <h4 style={{ margin: '0 0 0.35rem', fontSize: '0.9rem' }}>
                Metagame share (%)
              </h4>
              <ResponsiveContainer width="100%" height={120}>
                <LineChart data={weeks} margin={{ top: 6, right: 12, left: 28, bottom: 20 }}>
                  <XAxis dataKey="week_start" fontSize={11} tick={{ fill: 'var(--text-muted)' }} />
                  <YAxis width={30} fontSize={11} tick={{ fill: 'var(--text-muted)' }} domain={[0, 'auto']} />
                  <Tooltip
                    contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text)' }}
                    formatter={(value: number, _name, ctx: { payload?: { archetype_decks?: number; total_decks?: number } }) => [
                      `${value}% (${ctx.payload?.archetype_decks ?? 0}/${ctx.payload?.total_decks ?? 0})`,
                      'Share',
                    ]}
                    labelFormatter={(l) => `Week of ${l}`}
                  />
                  <Line type="monotone" dataKey="share_pct" stroke="var(--accent)" strokeWidth={2} dot={{ r: 2 }} name="Share %" />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div>
              <h4 style={{ margin: '0 0 0.35rem', fontSize: '0.9rem' }}>
                Top-8 rate (%)
              </h4>
              <ResponsiveContainer width="100%" height={120}>
                <LineChart data={weeks} margin={{ top: 6, right: 12, left: 28, bottom: 20 }}>
                  <XAxis dataKey="week_start" fontSize={11} tick={{ fill: 'var(--text-muted)' }} />
                  <YAxis width={30} fontSize={11} tick={{ fill: 'var(--text-muted)' }} domain={[0, 100]} />
                  <Tooltip
                    contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text)' }}
                    formatter={(value: number, _name, ctx: { payload?: { archetype_top8?: number; archetype_decks?: number } }) => [
                      `${value}% (${ctx.payload?.archetype_top8 ?? 0}/${ctx.payload?.archetype_decks ?? 0})`,
                      'Top-8 rate',
                    ]}
                    labelFormatter={(l) => `Week of ${l}`}
                  />
                  <Line type="monotone" dataKey="top8_rate_pct" stroke="#22c55e" strokeWidth={2} dot={{ r: 2 }} name="Top-8 %" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

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
        {hasManaPips && (
          <div className="chart-container">
            <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Mana demand by color</h4>
            <p style={{ margin: '0 0 0.5rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Average colored pips per deck from non-land cards. Helps size your mana base by color.
            </p>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={manaPipsData} margin={{ top: 10, right: 16, left: 24, bottom: 16 }}>
                <XAxis dataKey="color" tick={{ fill: 'var(--text-muted)' }} />
                <YAxis width={28} tick={{ fill: 'var(--text-muted)' }} />
                <Tooltip
                  contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text)' }}
                  formatter={(value: number, _name, ctx: { payload?: { label?: string } }) => [`${value} pips`, ctx.payload?.label ?? '']}
                />
                <Bar dataKey="pips" name="Avg pips">
                  {manaPipsData.map((d) => (
                    <Cell key={d.color} fill={d.fill} />
                  ))}
                </Bar>
              </BarChart>
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

      {topPlayers.length > 0 && (
        <div className="chart-container" style={{ marginTop: '1.5rem' }}>
          <h3 style={{ margin: '0 0 0.5rem' }}>Top pilots</h3>
          <p style={{ margin: '0 0 0.75rem', fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
            Best performing players on this archetype in the selected timeframe.
          </p>
          <div className="table-wrap-outer">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">#</th>
                    <th scope="col">Player</th>
                    <th scope="col" title="Decks of this archetype piloted">Decks</th>
                    <th scope="col">Wins</th>
                    <th scope="col">Top 2</th>
                    <th scope="col">Top 4</th>
                    <th scope="col">Top 8</th>
                    <th scope="col" title="Placement-weighted score">Points</th>
                  </tr>
                </thead>
                <tbody>
                  {topPlayers.map((p, i) => (
                    <tr key={`${p.player}-${i}`}>
                      <td style={{ color: 'var(--text-muted)' }}>{i + 1}</td>
                      <td>
                        <Link to={`/players/${encodeURIComponent(p.player)}`} style={{ color: 'var(--accent)' }}>
                          {p.player}
                        </Link>
                      </td>
                      <td>{p.deck_count}</td>
                      <td>{p.wins}</td>
                      <td>{p.top2}</td>
                      <td>{p.top4}</td>
                      <td>{p.top8}</td>
                      <td>{Math.round(p.points * 10) / 10}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {typicalList && bucketMeta.some((b) => typicalList[b.key].length > 0) && (
        <div className="chart-container" style={{ marginTop: '1.5rem' }}>
          <h3 style={{ margin: '0 0 0.5rem' }}>Typical list</h3>
          <p style={{ margin: '0 0 0.75rem', fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
            Cards grouped by how often they appear in this archetype. Core = near-mandatory, Staple = common, Flex = optional, Tech = niche.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {bucketMeta.map((b) => {
              const entries: TypicalListEntry[] = typicalList[b.key]
              if (!entries || entries.length === 0) return null
              const open = bucketOpen[b.key]
              return (
                <div key={b.key} style={{ border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden' }}>
                  <button
                    type="button"
                    onClick={() => setBucketOpen((s) => ({ ...s, [b.key]: !s[b.key] }))}
                    style={{
                      width: '100%',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      padding: '0.5rem 0.75rem',
                      background: 'var(--bg-card)',
                      border: 'none',
                      cursor: 'pointer',
                      color: 'inherit',
                      font: 'inherit',
                    }}
                    aria-expanded={open}
                  >
                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: b.color }} />
                      <strong>{b.title}</strong>
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.8125rem' }}>
                        {b.desc} · {entries.length} card{entries.length !== 1 ? 's' : ''}
                      </span>
                    </span>
                    <span style={{ color: 'var(--text-muted)' }}>{open ? '\u25BC' : '\u25B6'}</span>
                  </button>
                  {open && (
                    <div className="table-wrap-outer">
                      <div className="table-wrap">
                        <table>
                          <thead>
                            <tr>
                              <th scope="col">Card</th>
                              <th scope="col" title="% of decks in this archetype that run the card">Play rate</th>
                              <th scope="col" title="Average number of copies across all decks (including zeros)">Avg copies</th>
                              <th scope="col" title="Median copies among decks that run the card">Median</th>
                            </tr>
                          </thead>
                          <tbody>
                            {entries.map((e) => (
                              <tr key={e.card}>
                                <td>
                                  <CardHover cardName={e.card} linkTo>{e.card}</CardHover>
                                </td>
                                <td>{e.play_rate_pct}%</td>
                                <td>{e.mean_copies}</td>
                                <td>{e.median_copies}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      <div style={{ marginTop: '1.5rem' }}>
        <div className="chart-container" style={{ marginBottom: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '0.5rem' }}>
            <h3 style={{ margin: 0 }}>Card trends</h3>
            <div className="toolbar pill-group" style={{ gap: '0.35rem', alignItems: 'center', flexWrap: 'wrap' }}>
              <span style={{ color: 'var(--text-muted)', fontSize: '0.8125rem', fontWeight: 600 }}>Recent window:</span>
              {[
                { mode: 'events' as const, value: 3, label: 'Last 3 events' },
                { mode: 'events' as const, value: 5, label: 'Last 5 events' },
                { mode: 'days' as const, value: 30, label: 'Last 30 days' },
                { mode: 'days' as const, value: 90, label: 'Last 90 days' },
                { mode: 'ratio' as const, value: 30, label: 'Last 30% of decks' },
              ].map((preset) => {
                const active = recencyMode === preset.mode && recencyValue === preset.value
                return (
                  <button
                    key={`${preset.mode}-${preset.value}`}
                    type="button"
                    className="btn"
                    style={{
                      padding: '0.2rem 0.55rem',
                      fontSize: '0.8rem',
                      background: active ? 'var(--accent)' : undefined,
                      color: active ? '#fff' : undefined,
                      borderColor: active ? 'var(--accent)' : undefined,
                    }}
                    onClick={() => { setRecencyMode(preset.mode); setRecencyValue(preset.value) }}
                    aria-pressed={active}
                  >
                    {preset.label}
                  </button>
                )
              })}
              <button
                type="button"
                className="btn"
                style={{
                  padding: '0.2rem 0.55rem',
                  fontSize: '0.8rem',
                  background: recencyMode === 'custom' ? 'var(--accent)' : undefined,
                  color: recencyMode === 'custom' ? '#fff' : undefined,
                  borderColor: recencyMode === 'custom' ? 'var(--accent)' : undefined,
                }}
                onClick={() => setRecencyMode('custom')}
                aria-pressed={recencyMode === 'custom'}
              >
                Custom…
              </button>
              {recencyMode === 'custom' && (
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.8rem' }}>
                  <span style={{ color: 'var(--text-muted)' }}>From (DD/MM/YY):</span>
                  <input
                    type="text"
                    value={customRecentFrom}
                    onChange={(e) => setCustomRecentFrom(e.target.value)}
                    placeholder="01/01/26"
                    style={{ width: 92, padding: '0.2rem 0.35rem', fontSize: '0.8rem' }}
                    aria-label="Recent window start date"
                  />
                </label>
              )}
            </div>
          </div>
          {trends && (
            <p style={{ margin: 0, fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
              Recent: {trends.recent.date_from ?? '—'} → {trends.recent.date_to ?? '—'} · {trends.recent.deck_count} deck{trends.recent.deck_count !== 1 ? 's' : ''} / {trends.recent.event_count} event{trends.recent.event_count !== 1 ? 's' : ''}
              {'  ·  '}
              Older: {trends.older.date_from ?? '—'} → {trends.older.date_to ?? '—'} · {trends.older.deck_count} deck{trends.older.deck_count !== 1 ? 's' : ''} / {trends.older.event_count} event{trends.older.event_count !== 1 ? 's' : ''}
            </p>
          )}
          {loadingTrends && !trends && (
            <p style={{ margin: 0, fontSize: '0.8125rem', color: 'var(--text-muted)' }}>Loading trends…</p>
          )}
          {trendsError && (
            <p style={{ margin: 0, fontSize: '0.8125rem', color: 'var(--danger, #ef4444)' }}>{trendsError}</p>
          )}
          {trends?.warning && (
            <p style={{ margin: '0.35rem 0 0', fontSize: '0.8125rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
              {trends.warning}
            </p>
          )}
        </div>

        <div className="deck-analysis-grid">
          <div className="chart-container">
            <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.95rem' }}>New cards</h4>
            <p style={{ margin: '0 0 0.75rem', fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
              Cards appearing in the recent window but largely absent from older lists.
            </p>
            {trends && trends.new_cards.length > 0 ? (
              <div className="table-wrap-outer">
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th scope="col">#</th>
                        <th scope="col">Card</th>
                        <th scope="col" title="% of recent decks playing the card">Recent %</th>
                        <th scope="col" title="% of older decks playing the card">Older %</th>
                        <th scope="col" title="Recent − Older">Δ</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trends.new_cards.map((c, i) => (
                        <tr key={c.card}>
                          <td style={{ color: 'var(--text-muted)' }}>{i + 1}</td>
                          <td>
                            <CardHover cardName={c.card} linkTo>{c.card}</CardHover>
                          </td>
                          <td title={`${c.recent_decks} recent decks`}>{c.recent_play_rate_pct}%</td>
                          <td title={`${c.older_decks} older decks`}>{c.older_play_rate_pct}%</td>
                          <td style={{ color: 'var(--success, #22c55e)', fontWeight: 600 }}>+{c.delta_pct}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', margin: 0 }}>
                {loadingTrends ? 'Loading…' : 'No new cards detected. Try a larger recent window.'}
              </p>
            )}
          </div>

          <div className="chart-container">
            <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.95rem' }}>Legacy cards</h4>
            <p style={{ margin: '0 0 0.75rem', fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
              Cards common in older lists but rarely played in the recent window.
            </p>
            {trends && trends.legacy_cards.length > 0 ? (
              <div className="table-wrap-outer">
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th scope="col">#</th>
                        <th scope="col">Card</th>
                        <th scope="col" title="% of recent decks playing the card">Recent %</th>
                        <th scope="col" title="% of older decks playing the card">Older %</th>
                        <th scope="col" title="Older − Recent">Δ</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trends.legacy_cards.map((c, i) => (
                        <tr key={c.card}>
                          <td style={{ color: 'var(--text-muted)' }}>{i + 1}</td>
                          <td>
                            <CardHover cardName={c.card} linkTo>{c.card}</CardHover>
                          </td>
                          <td title={`${c.recent_decks} recent decks`}>{c.recent_play_rate_pct}%</td>
                          <td title={`${c.older_decks} older decks`}>{c.older_play_rate_pct}%</td>
                          <td style={{ color: 'var(--danger, #ef4444)', fontWeight: 600 }}>−{c.delta_pct}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', margin: 0 }}>
                {loadingTrends ? 'Loading…' : 'No legacy cards detected. Try a larger recent window.'}
              </p>
            )}
          </div>
        </div>
      </div>

      {matchupRowsFiltered.length > 0 && (
        <div style={{ marginTop: '1.5rem' }}>
          <h3 style={{ margin: '0 0 0.75rem' }}>Matchup performance</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '0.5rem' }}>
            From event feedback. Same-archetype matchups excluded. <Link to="/matchups">View full matchups</Link>
          </p>
          {matchupHeatRows.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '0.75rem' }}>
              {bestMatchups.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.35rem' }}>
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.8125rem', fontWeight: 600 }}>Favorable:</span>
                  {bestMatchups.map((row, i) => (
                    <span
                      key={`best-${i}`}
                      title={`${row.wins}-${row.losses}-${row.draws} over ${row.matches} matches`}
                      style={{
                        padding: '0.15rem 0.5rem',
                        borderRadius: 999,
                        background: 'rgba(34, 197, 94, 0.18)',
                        border: '1px solid rgba(34, 197, 94, 0.4)',
                        color: 'var(--text)',
                        fontSize: '0.8125rem',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {row.opponent_archetype}{' '}
                      <strong style={{ color: '#22c55e' }}>{(row.win_rate * 100).toFixed(0)}%</strong>
                      <span style={{ color: 'var(--text-muted)' }}> ({row.matches})</span>
                    </span>
                  ))}
                </div>
              )}
              {worstMatchups.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.35rem' }}>
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.8125rem', fontWeight: 600 }}>Unfavorable:</span>
                  {worstMatchups.map((row, i) => (
                    <span
                      key={`worst-${i}`}
                      title={`${row.wins}-${row.losses}-${row.draws} over ${row.matches} matches`}
                      style={{
                        padding: '0.15rem 0.5rem',
                        borderRadius: 999,
                        background: 'rgba(239, 68, 68, 0.18)',
                        border: '1px solid rgba(239, 68, 68, 0.4)',
                        color: 'var(--text)',
                        fontSize: '0.8125rem',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {row.opponent_archetype}{' '}
                      <strong style={{ color: '#ef4444' }}>{(row.win_rate * 100).toFixed(0)}%</strong>
                      <span style={{ color: 'var(--text-muted)' }}> ({row.matches})</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
          <div className="table-wrap-outer">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col" aria-sort={matchupAriaSort('opponent_archetype')}>
                      <button
                        type="button"
                        className="th-sort"
                        onClick={() => handleMatchupSort('opponent_archetype')}
                        style={{ background: 'none', border: 'none', padding: 0, font: 'inherit', cursor: 'pointer', color: 'inherit' }}
                      >
                        Opponent archetype{matchupSortArrow('opponent_archetype')}
                      </button>
                    </th>
                    <th scope="col" aria-sort={matchupAriaSort('record')}>
                      <button
                        type="button"
                        className="th-sort"
                        onClick={() => handleMatchupSort('record')}
                        style={{ background: 'none', border: 'none', padding: 0, font: 'inherit', cursor: 'pointer', color: 'inherit' }}
                      >
                        Record{matchupSortArrow('record')}
                      </button>
                    </th>
                    <th scope="col" aria-sort={matchupAriaSort('win_rate')}>
                      <button
                        type="button"
                        className="th-sort"
                        onClick={() => handleMatchupSort('win_rate')}
                        style={{ background: 'none', border: 'none', padding: 0, font: 'inherit', cursor: 'pointer', color: 'inherit' }}
                      >
                        Win rate{matchupSortArrow('win_rate')}
                      </button>
                    </th>
                    <th scope="col" aria-sort={matchupAriaSort('matches')}>
                      <button
                        type="button"
                        className="th-sort"
                        onClick={() => handleMatchupSort('matches')}
                        style={{ background: 'none', border: 'none', padding: 0, font: 'inherit', cursor: 'pointer', color: 'inherit' }}
                      >
                        Matches{matchupSortArrow('matches')}
                      </button>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {matchupRowsSorted.map((row, i) => (
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
