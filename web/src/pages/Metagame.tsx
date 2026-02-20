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
import { getMetagame, getDateRange, getFormatInfo, getEvents, getCardLookup } from '../api'
import type { CardLookupResult } from '../api'
import CardHover from '../components/CardHover'
import EventSelector from '../components/EventSelector'
import ManaSymbols from '../components/ManaSymbols'
import Skeleton from '../components/Skeleton'
import type { MetagameReport, Event } from '../types'

const COLORS = ['#1d9bf0', '#00ba7c', '#f7931a', '#e91e63', '#9c27b0', '#00bcd4', '#ff9800', '#4caf50']

const TYPE_ORDER = ['Land', 'Creature', 'Instant', 'Sorcery', 'Enchantment', 'Artifact', 'Planeswalker']
/** Returns all card types present in type_line (e.g. "Enchantment Land — Saga" → ["Enchantment", "Land"]). */
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
const CMC_OPTIONS = [0, 1, 2, 3, 4, 5] // 5 means 5+
const TYPE_OPTIONS = [...TYPE_ORDER, 'Other']

const FILTER_SYMBOL_SIZE = 20

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
  const [cardMeta, setCardMeta] = useState<Record<string, CardLookupResult>>({})
  const [loadingCardMeta, setLoadingCardMeta] = useState(false)
  const [filterColor, setFilterColor] = useState<string[]>([])
  const [filterCmc, setFilterCmc] = useState<number[]>([])
  const [filterType, setFilterType] = useState<string[]>([])
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
      .catch((e) => {
        setError(e.message)
        toast.error(e.message)
      })
      .finally(() => setLoading(false))
  }, [placementWeighted, ignoreLands, eventIds])

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
              const eventIdsParam = eventIds.length ? eventIds.join(',') : undefined
              getMetagame(placementWeighted, ignoreLands, undefined, undefined, undefined, eventIdsParam)
                .then(setMetagame)
                .catch((e) => {
                  setError(e.message)
                  toast.error(e.message)
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

  const hasAnyFilter = filterColor.length > 0 || filterCmc.length > 0 || filterType.length > 0
  const filteredTopCards = topMain.filter((c) => {
    const m = cardMeta[c.card]
    if (!m || m.error) return !hasAnyFilter
    const colors = m.color_identity ?? m.colors ?? []
    const cat = colorCategory(colors)
    const cmc = m.cmc
    const bucket = cmcBucket(cmc)
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '0.75rem' }}>
        <h1 className="page-title" style={{ margin: 0 }}>
          Metagame Analysis{formatName && <span style={{ fontSize: '0.7em', color: 'var(--text-muted)', marginLeft: '0.5rem' }}>— {formatName}</span>}
        </h1>
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
              if (state?.activeLabel) navigate(`/decks?deck_name=${encodeURIComponent(state.activeLabel)}`)
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
        <h3 style={{ margin: '0 0 1rem' }}>
          Archetype Distribution (Top 8)
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
            <Tooltip />
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
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
          <h3 style={{ margin: 0 }}>
            Top Cards (Mainboard)
            {placementWeighted && <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginLeft: '0.5rem' }}>sorted by weighted score</span>}
          </h3>
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
        </div>

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
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={ignoreLands}
                onChange={(e) => setIgnoreLands(e.target.checked)}
                aria-label="Ignore lands"
              />
              Ignore lands
            </label>
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

        {loadingCardMeta && (
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '0.5rem' }}>Loading card data…</p>
        )}
        {hasAnyFilter && filteredTotal === 0 && !loadingCardMeta && (
          <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>No cards match the current filters.</p>
        )}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">#</th>
                <th scope="col">Card</th>
                <th scope="col">Decks</th>
                <th scope="col">Play Rate</th>
                <th scope="col">{placementWeighted ? 'Weighted Score' : 'Copies'}</th>
              </tr>
            </thead>
            <tbody>
              {topCardsSlice.map((c, i) => (
                <tr key={c.card}>
                  <td style={{ color: 'var(--text-muted)' }}>{safePage * TOP_CARDS_PER_PAGE + i + 1}</td>
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
      )}
    </div>
  )
}
