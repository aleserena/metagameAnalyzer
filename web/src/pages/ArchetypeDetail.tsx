import { useEffect, useState } from 'react'
import { useParams, useSearchParams, useNavigate, Link } from 'react-router-dom'
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
import { getArchetypeDetail, getCardLookup, getDecks } from '../api'
import type { CardLookupResult } from '../api'
import type { ArchetypeDetail as ArchetypeDetailType, Deck } from '../types'
import CardHover from '../components/CardHover'
import ManaSymbols from '../components/ManaSymbols'
import Skeleton from '../components/Skeleton'
import { reportError } from '../utils'

const TYPE_ORDER = ['Land', 'Creature', 'Instant', 'Sorcery', 'Enchantment', 'Artifact', 'Planeswalker']
function getCardTypes(typeLine: string | undefined): string[] {
  if (!typeLine) return ['Other']
  const upper = typeLine.toUpperCase()
  const types = TYPE_ORDER.filter((t) => upper.includes(t.toUpperCase()))
  return types.length > 0 ? types : ['Other']
}
function colorCategory(colors: string[] | undefined): string {
  if (!colors || colors.length === 0) return 'Colorless'
  if (colors.length >= 2) return 'Multicolor'
  return colors[0]!
}
function cmcBucket(cmc: number | undefined): number {
  if (typeof cmc !== 'number' || cmc < 0) return 0
  return cmc >= 5 ? 5 : cmc
}
const COLOR_OPTIONS: { value: string; manaCost: string | null; title: string }[] = [
  { value: 'W', manaCost: '{W}', title: 'White' },
  { value: 'U', manaCost: '{U}', title: 'Blue' },
  { value: 'B', manaCost: '{B}', title: 'Black' },
  { value: 'R', manaCost: '{R}', title: 'Red' },
  { value: 'G', manaCost: '{G}', title: 'Green' },
  { value: 'Colorless', manaCost: '{C}', title: 'Colorless' },
  { value: 'Multicolor', manaCost: null, title: 'Multicolor' },
]
const CMC_OPTIONS = [0, 1, 2, 3, 4, 5]
const TYPE_OPTIONS = [...TYPE_ORDER, 'Other']
const FILTER_SYMBOL_SIZE = 20
const TOP_CARDS_PER_PAGE = 50

export default function ArchetypeDetail() {
  const { archetypeName } = useParams<{ archetypeName: string }>()
  const [searchParams] = useSearchParams()
  const [detail, setDetail] = useState<ArchetypeDetailType | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [cardMeta, setCardMeta] = useState<Record<string, CardLookupResult>>({})
  const [loadingCardMeta, setLoadingCardMeta] = useState(false)
  const [filterColor, setFilterColor] = useState<string[]>([])
  const [filterCmc, setFilterCmc] = useState<number[]>([])
  const [filterType, setFilterType] = useState<string[]>([])
  const [topCardsPage, setTopCardsPage] = useState(0)
  const [topDecks, setTopDecks] = useState<Deck[]>([])

  const navigate = useNavigate()
  const eventIdsParam = searchParams.get('event_ids') ?? undefined

  useEffect(() => {
    if (!archetypeName) return
    setLoading(true)
    setNotFound(false)
    getArchetypeDetail(decodeURIComponent(archetypeName), {
      eventIds: eventIdsParam ?? undefined,
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
  const hasAnyFilter = filterColor.length > 0 || filterCmc.length > 0 || filterType.length > 0
  const filteredTopCards = topMain.filter((c) => {
    const m = cardMeta[c.card]
    if (!m || 'error' in m) return !hasAnyFilter
    const colors = m.color_identity ?? m.colors ?? []
    const cat = colorCategory(colors)
    const bucket = cmcBucket(m.cmc)
    const cardTypes = getCardTypes(m.type_line)
    if (filterColor.length > 0 && !filterColor.includes(cat)) return false
    if (filterCmc.length > 0 && !filterCmc.includes(bucket)) return false
    if (filterType.length > 0 && !filterType.some((t) => cardTypes.includes(t))) return false
    return true
  })
  const filteredTotal = filteredTopCards.length
  const filteredPages = Math.ceil(filteredTotal / TOP_CARDS_PER_PAGE)
  const safePage = Math.min(topCardsPage, Math.max(0, filteredPages - 1))
  const topCardsSlice = filteredTopCards.slice(
    safePage * TOP_CARDS_PER_PAGE,
    (safePage + 1) * TOP_CARDS_PER_PAGE
  )
  const setFilterColorAndResetPage = (v: string[]) => {
    setFilterColor(v)
    setTopCardsPage(0)
  }
  const setFilterCmcAndResetPage = (v: number[]) => {
    setFilterCmc(v)
    setTopCardsPage(0)
  }
  const setFilterTypeAndResetPage = (v: string[]) => {
    setFilterType(v)
    setTopCardsPage(0)
  }
  const clearFilters = () => {
    setFilterColor([])
    setFilterCmc([])
    setFilterType([])
    setTopCardsPage(0)
  }

  return (
    <div style={{ opacity: loading ? 0.6 : 1, transition: 'opacity 0.2s' }}>
      <button type="button" className="btn" style={{ marginBottom: '1rem' }} onClick={() => navigate(-1)}>
        Back
      </button>
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 className="page-title" style={{ margin: 0 }}>
          {detail.archetype}
        </h1>
        <p style={{ margin: '0.25rem 0 0', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
          Average of {detail.deck_count} deck{detail.deck_count !== 1 ? 's' : ''}
          {eventIdsParam && ' in selected events'}
        </p>
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
              <BarChart
                data={Object.entries(a.mana_curve).map(([cmc, count]) => ({ cmc: Number(cmc), count }))}
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
                <Bar dataKey="count" fill="#1d9bf0" name="Cards (avg)" />
              </BarChart>
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
                    { name: 'White', value: a.color_distribution.W || 0, color: '#fff9e6' },
                    { name: 'Blue', value: a.color_distribution.U || 0, color: '#0e4d92' },
                    { name: 'Black', value: a.color_distribution.B || 0, color: '#8b8b8b' },
                    { name: 'Red', value: a.color_distribution.R || 0, color: '#c41e3a' },
                    { name: 'Green', value: a.color_distribution.G || 0, color: '#007a33' },
                    { name: 'Colorless', value: a.color_distribution.C || 0, color: '#b0b0b0' },
                  ].filter((d) => d.value > 0)}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={58}
                >
                  {[
                    { name: 'White', value: a.color_distribution.W || 0, color: '#fff9e6' },
                    { name: 'Blue', value: a.color_distribution.U || 0, color: '#0e4d92' },
                    { name: 'Black', value: a.color_distribution.B || 0, color: '#8b8b8b' },
                    { name: 'Red', value: a.color_distribution.R || 0, color: '#c41e3a' },
                    { name: 'Green', value: a.color_distribution.G || 0, color: '#007a33' },
                    { name: 'Colorless', value: a.color_distribution.C || 0, color: '#b0b0b0' },
                  ]
                    .filter((d) => d.value > 0)
                    .map((d) => (
                      <Cell key={d.name} fill={d.color} />
                    ))}
                </Pie>
                <Tooltip />
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
                <Tooltip />
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
                <Tooltip />
                <Legend layout="horizontal" verticalAlign="bottom" wrapperStyle={{ paddingTop: 4 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      <div className="chart-container" style={{ marginTop: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
          <h3 style={{ margin: 0 }}>Most played cards</h3>
          {topMain.length > 0 && (
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                {filteredTotal === 0 ? '0' : `${safePage * TOP_CARDS_PER_PAGE + 1}–${Math.min((safePage + 1) * TOP_CARDS_PER_PAGE, filteredTotal)}`} of {filteredTotal}
              </span>
              <button
                type="button"
                className="btn"
                style={{ padding: '0.2rem 0.5rem', fontSize: '0.8rem' }}
                disabled={safePage === 0}
                onClick={() => setTopCardsPage((p) => Math.max(0, p - 1))}
              >
                Prev
              </button>
              <button
                type="button"
                className="btn"
                style={{ padding: '0.2rem 0.5rem', fontSize: '0.8rem' }}
                disabled={filteredTotal <= TOP_CARDS_PER_PAGE || safePage >= filteredPages - 1}
                onClick={() => setTopCardsPage((p) => Math.min(filteredPages - 1, p + 1))}
              >
                Next
              </button>
            </div>
          )}
        </div>

        {topMain.length > 0 && (
          <div
            className="top-cards-filters"
            style={{
              padding: '0.5rem 0.75rem',
              background: 'var(--bg)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              marginBottom: '1rem',
              fontSize: '0.8125rem',
            }}
          >
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center' }}>
              <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>Filter:</span>
              <span style={{ fontWeight: 600 }}>Color</span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', alignItems: 'center' }}>
                {COLOR_OPTIONS.map((opt) => (
                  <label key={opt.value} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', cursor: 'pointer', fontSize: '0.8rem' }} title={opt.title}>
                    <input
                      type="checkbox"
                      checked={filterColor.includes(opt.value)}
                      onChange={(e) => {
                        if (e.target.checked) setFilterColorAndResetPage([...filterColor, opt.value])
                        else setFilterColorAndResetPage(filterColor.filter((x) => x !== opt.value))
                      }}
                      disabled={loadingCardMeta}
                    />
                    {opt.manaCost ? (
                      <ManaSymbols manaCost={opt.manaCost} size={FILTER_SYMBOL_SIZE} />
                    ) : (
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          width: FILTER_SYMBOL_SIZE,
                          height: FILTER_SYMBOL_SIZE,
                          borderRadius: '50%',
                          background: '#c9b037',
                          color: '#1a1a1a',
                          fontSize: 11,
                          fontWeight: 700,
                        }}
                      >
                        M
                      </span>
                    )}
                  </label>
                ))}
              </div>
              <span style={{ fontWeight: 600 }}>Cost</span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', alignItems: 'center' }}>
                {CMC_OPTIONS.map((opt) => (
                  <label key={opt} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', cursor: 'pointer', fontSize: '0.8rem' }} title={opt === 5 ? '5+' : `CMC ${opt}`}>
                    <input
                      type="checkbox"
                      checked={filterCmc.includes(opt)}
                      onChange={(e) => {
                        if (e.target.checked) setFilterCmcAndResetPage([...filterCmc, opt])
                        else setFilterCmcAndResetPage(filterCmc.filter((x) => x !== opt))
                      }}
                      disabled={loadingCardMeta}
                    />
                    <ManaSymbols manaCost={`{${opt}}`} size={FILTER_SYMBOL_SIZE} />
                  </label>
                ))}
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', alignItems: 'center' }}>
                <span style={{ fontWeight: 600 }}>Type</span>
                {TYPE_OPTIONS.map((opt) => (
                  <label key={opt} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', cursor: 'pointer', fontSize: '0.8rem' }}>
                    <input
                      type="checkbox"
                      checked={filterType.includes(opt)}
                      onChange={(e) => {
                        if (e.target.checked) setFilterTypeAndResetPage([...filterType, opt])
                        else setFilterTypeAndResetPage(filterType.filter((x) => x !== opt))
                      }}
                      disabled={loadingCardMeta}
                    />
                    {opt}
                  </label>
                ))}
              </div>
              <button
                type="button"
                className="btn"
                style={{ padding: '0.2rem 0.5rem', fontSize: '0.8rem' }}
                onClick={clearFilters}
                disabled={!hasAnyFilter}
              >
                Clear filters
              </button>
            </div>
          </div>
        )}

        {loadingCardMeta && <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '0.5rem' }}>Loading card data…</p>}
        {hasAnyFilter && filteredTotal === 0 && !loadingCardMeta && (
          <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>No cards match the current filters.</p>
        )}
        {detail.top_cards_main.length === 0 ? (
          <p style={{ color: 'var(--text-muted)' }}>No card data.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Card</th>
                  <th style={{ textAlign: 'right' }}>In decks</th>
                  <th style={{ textAlign: 'right' }}>Total copies</th>
                </tr>
              </thead>
              <tbody>
                {topCardsSlice.map((c, i) => (
                  <tr key={c.card}>
                    <td style={{ color: 'var(--text-muted)' }}>{safePage * TOP_CARDS_PER_PAGE + i + 1}</td>
                    <td>
                      <CardHover cardName={c.card}>
                        <span style={{ cursor: 'pointer', color: 'var(--accent)' }}>{c.card}</span>
                      </CardHover>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      {c.decks} in {c.play_rate_pct}% of decks
                    </td>
                    <td style={{ textAlign: 'right' }}>{c.total_copies}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
