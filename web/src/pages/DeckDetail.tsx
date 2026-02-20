import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from 'recharts'
import { getDeck, getMetagame, getDeckAnalysis, getDateRange, getSimilarDecks } from '../api'
import type { Deck, MetagameReport, SimilarDeck } from '../types'
import type { DeckAnalysis, CardMeta } from '../api'
import CardGrid from '../components/CardGrid'
import CardHover from '../components/CardHover'
import ManaSymbols from '../components/ManaSymbols'
import { dateMinusDays, firstDayOfYear, pluralizeType } from '../utils'

type ViewMode = 'list' | 'scryfall'
type GroupMode = 'type' | 'cmc' | 'color' | 'none'
type SortMode = 'name' | 'cmc'

const COLOR_LABELS: Record<string, string> = {
  W: 'White', U: 'Blue', B: 'Black', R: 'Red', G: 'Green',
  C: 'Colorless', M: 'Multicolor', Land: 'Land',
}

function groupLabel(mode: GroupMode, key: string): string {
  if (mode === 'type') return pluralizeType(key)
  if (mode === 'color') return COLOR_LABELS[key] ?? key
  if (mode === 'cmc') return key === '0' ? 'CMC 0' : `CMC ${key}`
  return key
}

function getGroupedData(
  analysis: DeckAnalysis | null,
  mode: GroupMode,
  section: 'main' | 'side',
): Record<string, [number, string][]> | null {
  if (!analysis) return null
  if (mode === 'type') return section === 'main' ? analysis.grouped_by_type ?? null : analysis.grouped_by_type_sideboard ?? null
  if (mode === 'cmc') return section === 'main' ? analysis.grouped_by_cmc ?? null : analysis.grouped_by_cmc_sideboard ?? null
  if (mode === 'color') return section === 'main' ? analysis.grouped_by_color ?? null : analysis.grouped_by_color_sideboard ?? null
  return null
}

function CardRow({
  qty, card, meta, highlight, showVsMetagame, playRate,
}: {
  qty: number; card: string; meta?: CardMeta; highlight: string | null
  showVsMetagame: boolean; playRate?: number
}) {
  return (
    <div
      className="card-row"
      style={{
        display: 'grid',
        gridTemplateColumns: '24px 1fr auto',
        gap: '0.35rem',
        alignItems: 'center',
        padding: '1px 0',
        color: highlight === 'above' ? 'var(--success)' : highlight === 'below' ? '#f44336' : undefined,
      }}
    >
      <span className="qty">{qty}</span>
      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        <CardHover cardName={card} linkTo>{card}</CardHover>
      </span>
      <span style={{ whiteSpace: 'nowrap', display: 'inline-flex', alignItems: 'center', gap: 2 }}>
        {meta ? <ManaSymbols manaCost={meta.mana_cost} size={14} /> : null}
        {showVsMetagame && playRate != null && (
          <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', marginLeft: 4 }}>
            {playRate}%
          </span>
        )}
      </span>
    </div>
  )
}

function sortEntries(
  entries: [number, string][],
  cardMeta: Record<string, CardMeta> | undefined,
  sortMode: SortMode,
): [number, string][] {
  return [...entries].sort((a, b) => {
    const [, cardA] = a
    const [, cardB] = b
    if (sortMode === 'cmc') {
      const cmcA = cardMeta?.[cardA]?.cmc ?? 99
      const cmcB = cardMeta?.[cardB]?.cmc ?? 99
      if (cmcA !== cmcB) return cmcA - cmcB
    }
    return cardA.localeCompare(cardB, undefined, { sensitivity: 'base' })
  })
}

function CardListSection({
  cards, grouped, groupMode, sortMode, cardMeta, getCardHighlight, showVsMetagame, playRateByCard,
}: {
  cards: { qty: number; card: string }[]
  grouped: Record<string, [number, string][]> | null
  groupMode: GroupMode
  sortMode: SortMode
  cardMeta?: Record<string, CardMeta>
  getCardHighlight: (card: string) => string | null
  showVsMetagame: boolean
  playRateByCard: Record<string, number>
}) {
  const renderCards = (entries: [number, string][]) =>
    sortEntries(entries, cardMeta, sortMode).map(([qty, card]) => (
      <CardRow
        key={card} qty={qty} card={card}
        meta={cardMeta?.[card]}
        highlight={getCardHighlight(card)}
        showVsMetagame={showVsMetagame}
        playRate={playRateByCard[card]}
      />
    ))

  if (grouped && groupMode !== 'none' && Object.keys(grouped).length > 0) {
    const groups = Object.entries(grouped)
    const midpoint = Math.ceil(
      groups.reduce((s, [, e]) => s + e.length, 0) / 2,
    )
    let count = 0
    let splitIdx = groups.length
    for (let i = 0; i < groups.length; i++) {
      count += groups[i][1].length
      if (count >= midpoint) { splitIdx = i + 1; break }
    }
    const col1 = groups.slice(0, splitIdx)
    const col2 = groups.slice(splitIdx)

    const renderColumn = (grps: [string, [number, string][]][]) =>
      grps.map(([key, entries]) => {
        const total = entries.reduce((s, [q]) => s + q, 0)
        return (
          <div key={key}>
            <div style={{ fontWeight: 600, marginTop: '0.5rem', marginBottom: '0.25rem', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              {groupLabel(groupMode, key)} ({total})
            </div>
            {renderCards(entries)}
          </div>
        )
      })

    return (
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
        <div className="deck-list">{renderColumn(col1)}</div>
        <div className="deck-list">{renderColumn(col2)}</div>
      </div>
    )
  }

  const entries = cards.map((c) => [c.qty, c.card] as [number, string])
  const sorted = sortEntries(entries, cardMeta, sortMode)
  const half = Math.ceil(sorted.length / 2)
  const col1 = sorted.slice(0, half)
  const col2 = sorted.slice(half)
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
      <div className="deck-list">
        {col1.map(([qty, card]) => (
          <CardRow
            key={card} qty={qty} card={card}
            meta={cardMeta?.[card]}
            highlight={getCardHighlight(card)}
            showVsMetagame={showVsMetagame}
            playRate={playRateByCard[card]}
          />
        ))}
      </div>
      <div className="deck-list">
        {col2.map(([qty, card]) => (
          <CardRow
            key={card} qty={qty} card={card}
            meta={cardMeta?.[card]}
            highlight={getCardHighlight(card)}
            showVsMetagame={showVsMetagame}
            playRate={playRateByCard[card]}
          />
        ))}
      </div>
    </div>
  )
}

export default function DeckDetail() {
  const { deckId } = useParams<{ deckId: string }>()
  const navigate = useNavigate()
  const [deck, setDeck] = useState<Deck | null>(null)
  const [metagame, setMetagame] = useState<MetagameReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showVsMetagame, setShowVsMetagame] = useState(false)
  const [viewMode, setViewMode] = useState<ViewMode>('list')
  const [groupMode, setGroupMode] = useState<GroupMode>('type')
  const [sortMode, setSortMode] = useState<SortMode>('cmc')
  const [analysis, setAnalysis] = useState<DeckAnalysis | null>(null)
  const [metagameDateFrom, setMetagameDateFrom] = useState<string | null>(null)
  const [metagameDateTo, setMetagameDateTo] = useState<string | null>(null)
  const [maxDate, setMaxDate] = useState<string | null>(null)
  const [lastEventDate, setLastEventDate] = useState<string | null>(null)
  const [similarDecks, setSimilarDecks] = useState<SimilarDeck[]>([])
  const [similarDecksSameEventOnly, setSimilarDecksSameEventOnly] = useState(true)
  const [compareSelectedIds, setCompareSelectedIds] = useState<Set<number>>(new Set())
  const MAX_COMPARE = 4

  useEffect(() => {
    if (!deckId) return
    getDeck(parseInt(deckId, 10))
      .then(setDeck)
      .catch((e) => {
        setError(e.message)
        toast.error(e.message)
      })
      .finally(() => setLoading(false))
  }, [deckId])

  useEffect(() => {
    getDateRange().then((r) => {
      setMaxDate(r.max_date)
      setLastEventDate(r.last_event_date)
    })
  }, [])

  useEffect(() => {
    if (!deckId || !showVsMetagame) return
    getMetagame(false, false, metagameDateFrom, metagameDateTo)
      .then(setMetagame)
      .catch(() => setMetagame(null))
  }, [deckId, showVsMetagame, metagameDateFrom, metagameDateTo])

  useEffect(() => {
    if (!deckId) return
    getDeckAnalysis(parseInt(deckId, 10))
      .then(setAnalysis)
      .catch(() => setAnalysis(null))
  }, [deckId])

  useEffect(() => {
    if (!deckId || !deck) return
    const eventIds = similarDecksSameEventOnly ? String(deck.event_id) : undefined
    getSimilarDecks(parseInt(deckId, 10), 8, eventIds)
      .then((r) => setSimilarDecks(r.similar))
      .catch(() => setSimilarDecks([]))
    setCompareSelectedIds(new Set())
  }, [deckId, deck, similarDecksSameEventOnly])

  if (loading) return <div className="loading">Loading...</div>
  if (error) {
    return (
      <div>
        <h1 className="page-title">Deck</h1>
        <div className="chart-container" style={{ textAlign: 'center', padding: '2rem' }}>
          <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>{error}</p>
          <button
            type="button"
            className="btn"
            onClick={() => {
              setError(null)
              setLoading(true)
              getDeck(parseInt(deckId!, 10))
                .then(setDeck)
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
  if (!deck) {
    toast.error('Deck not found')
    return (
      <div>
        <h1 className="page-title">Deck</h1>
        <div className="chart-container" style={{ textAlign: 'center', padding: '2rem' }}>
          <p style={{ color: 'var(--text-muted)' }}>Deck not found.</p>
          <button type="button" className="btn" style={{ marginTop: '1rem' }} onClick={() => navigate('/decks')}>
            Back to Decks
          </button>
        </div>
      </div>
    )
  }

  const playRateByCard: Record<string, number> = {}
  if (metagame) {
    for (const c of metagame.top_cards_main) {
      playRateByCard[c.card] = c.play_rate_pct
    }
  }
  const avgPlayRate =
    metagame && metagame.top_cards_main.length > 0
      ? metagame.top_cards_main.reduce((a, c) => a + c.play_rate_pct, 0) / metagame.top_cards_main.length
      : 0

  const getCardHighlight = (card: string) => {
    if (!showVsMetagame || !(card in playRateByCard)) return null
    const rate = playRateByCard[card]
    if (rate >= avgPlayRate * 1.2) return 'above'
    if (rate <= avgPlayRate * 0.5) return 'below'
    return null
  }

  return (
    <div>
      <button className="btn" style={{ marginBottom: '1rem' }} onClick={() => navigate(-1)}>
        Back
      </button>

      <h1 className="page-title">{deck.name}</h1>

      {deck.duplicate_info && (
        <div
          style={{
            marginBottom: '1rem',
            padding: '0.75rem 1rem',
            background: deck.duplicate_info.is_duplicate ? 'rgba(247, 147, 26, 0.15)' : 'rgba(0, 186, 124, 0.1)',
            border: `1px solid ${deck.duplicate_info.is_duplicate ? 'var(--warning)' : 'var(--success)'}`,
            borderRadius: 8,
            fontSize: '0.9rem',
          }}
        >
          {deck.duplicate_info.is_duplicate ? (
            <>
              <strong>Duplicate deck</strong> — Identical mainboard to{' '}
              {deck.duplicate_info.primary_deck ? (
                <Link to={`/decks/${deck.duplicate_info.duplicate_of}`} style={{ color: 'var(--accent)' }}>
                  {deck.duplicate_info.primary_deck.name}
                </Link>
              ) : (
                <Link to={`/decks/${deck.duplicate_info.duplicate_of}`} style={{ color: 'var(--accent)' }}>
                  another deck
                </Link>
              )}
              {deck.duplicate_info.primary_deck && (
                <span style={{ color: 'var(--text-muted)' }}>
                  {' '}({deck.duplicate_info.primary_deck.player} — {deck.duplicate_info.primary_deck.event_name} ({deck.duplicate_info.primary_deck.date}){deck.duplicate_info.primary_deck.rank ? ` — Rank ${deck.duplicate_info.primary_deck.rank}` : ''})
                </span>
              )}
              {deck.duplicate_info.same_mainboard_decks && deck.duplicate_info.same_mainboard_decks.length > 0 && (
                <div style={{ marginTop: '0.5rem' }}>
                  Other identical mainboard:{' '}
                  {deck.duplicate_info.same_mainboard_decks.map((d) => (
                    <span key={d.deck_id} style={{ marginRight: '1rem' }}>
                      <Link to={`/decks/${d.deck_id}`} style={{ color: 'var(--accent)' }}>{d.name}</Link>
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.85em' }}> — {d.player}, {d.event_name} ({d.date}){d.rank ? ` — Rank ${d.rank}` : ''}</span>
                    </span>
                  ))}
                </div>
              )}
            </>
          ) : (
            <>
              <strong>Has duplicates</strong> — {deck.duplicate_info.same_mainboard_ids.length} other deck(s) with identical mainboard
              {deck.duplicate_info.same_mainboard_decks && deck.duplicate_info.same_mainboard_decks.length > 0 ? (
                <ul style={{ listStyle: 'none', margin: '0.5rem 0 0', padding: 0 }}>
                  {deck.duplicate_info.same_mainboard_decks.map((d) => (
                    <li key={d.deck_id} style={{ padding: '0.25rem 0' }}>
                      <Link to={`/decks/${d.deck_id}`} style={{ color: 'var(--accent)' }}>{d.name}</Link>
                      <span style={{ color: 'var(--text-muted)', marginLeft: '0.5rem' }}>
                        {d.player} — {d.event_name} ({d.date}){d.rank ? ` — Rank ${d.rank}` : ''}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div style={{ marginTop: '0.5rem' }}>
                  {deck.duplicate_info.same_mainboard_ids.map((id) => (
                    <Link key={id} to={`/decks/${id}`} style={{ color: 'var(--accent)', marginRight: '1rem' }}>
                      View deck {id}
                    </Link>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      <div className="stat-card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: '1rem' }}>
          <div>
            <div className="label">Player</div>
            <div>
              <Link to={`/players/${encodeURIComponent(deck.player)}`} style={{ color: 'var(--accent)' }}>
                {deck.player}
              </Link>
            </div>
          </div>
          <div>
            <div className="label">Event</div>
            <div>
              <Link to={`/decks?event_ids=${deck.event_id}`} style={{ color: 'var(--accent)' }}>
                {deck.event_name}
              </Link>
            </div>
          </div>
          <div>
            <div className="label">Date</div>
            <div>{deck.date}</div>
          </div>
          <div>
            <div className="label">Rank</div>
            <div>{deck.rank || '-'}</div>
          </div>
          <div>
            <div className="label">Archetype</div>
            <div>{deck.archetype ? <Link to={`/decks?archetype=${encodeURIComponent(deck.archetype)}`} style={{ color: 'var(--accent)' }}>{deck.archetype}</Link> : '-'}</div>
          </div>
        </div>
      </div>

      {analysis && (
        <div style={{ marginBottom: '1rem' }}>
          <h3 style={{ margin: '0 0 0.5rem' }}>Deck Analysis</h3>
          <div className="deck-analysis-grid">
            <div className="chart-container">
              <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Mana Curve</h4>
              <ResponsiveContainer width="100%" height={180}>
                <BarChart
                  data={Object.entries(analysis.mana_curve).map(([cmc, count]) => ({ cmc: Number(cmc), count }))}
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
                  <Bar dataKey="count" fill="#1d9bf0" name="Cards" />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="chart-container">
              <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Color Distribution</h4>
              <ResponsiveContainer width="100%" height={200}>
                <PieChart margin={{ top: 8, right: 8, bottom: 58, left: 8 }}>
                  <Pie
                    data={[
                      { name: 'White', value: analysis.color_distribution.W || 0, color: '#fff9e6' },
                      { name: 'Blue', value: analysis.color_distribution.U || 0, color: '#0e4d92' },
                      { name: 'Black', value: analysis.color_distribution.B || 0, color: '#8b8b8b' },
                      { name: 'Red', value: analysis.color_distribution.R || 0, color: '#c41e3a' },
                      { name: 'Green', value: analysis.color_distribution.G || 0, color: '#007a33' },
                      { name: 'Colorless', value: analysis.color_distribution.C || 0, color: '#b0b0b0' },
                    ].filter((d) => d.value > 0)}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={58}
                  >
                    {[
                      { name: 'White', value: analysis.color_distribution.W || 0, color: '#fff9e6' },
                      { name: 'Blue', value: analysis.color_distribution.U || 0, color: '#0e4d92' },
                      { name: 'Black', value: analysis.color_distribution.B || 0, color: '#8b8b8b' },
                      { name: 'Red', value: analysis.color_distribution.R || 0, color: '#c41e3a' },
                      { name: 'Green', value: analysis.color_distribution.G || 0, color: '#007a33' },
                      { name: 'Colorless', value: analysis.color_distribution.C || 0, color: '#b0b0b0' },
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
            <div className="chart-container">
              <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Lands Distribution</h4>
              <ResponsiveContainer width="100%" height={200}>
                <PieChart margin={{ top: 8, right: 8, bottom: 58, left: 8 }}>
                  <Pie
                    data={[
                      { name: 'Lands', value: analysis.lands_distribution.lands, color: '#8b7355' },
                      { name: 'Non-Lands', value: analysis.lands_distribution.nonlands, color: '#1d9bf0' },
                    ].filter((d) => d.value > 0)}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={58}
                  >
                    {[
                      { name: 'Lands', value: analysis.lands_distribution.lands, color: '#8b7355' },
                      { name: 'Non-Lands', value: analysis.lands_distribution.nonlands, color: '#1d9bf0' },
                    ]
                      .filter((d) => d.value > 0)
                      .map((d) => (
                        <Cell key={d.name} fill={d.color} />
                      ))}
                  </Pie>
                  <Tooltip />
                  <Legend layout="horizontal" verticalAlign="bottom" formatter={(_, entry: { payload?: { name?: string; value?: number } }) => {
                    const p = entry?.payload
                    if (!p) return ''
                    const total = analysis.lands_distribution.lands + analysis.lands_distribution.nonlands
                    const pct = total ? Math.round((100 * (p.value ?? 0)) / total) : 0
                    return `${p.name ?? ''} ${p.value ?? ''} (${pct}%)`
                  }} wrapperStyle={{ paddingTop: 4 }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            {analysis.type_distribution && Object.keys(analysis.type_distribution).length > 0 && (
              <div className="chart-container">
                <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Card Type Distribution</h4>
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart margin={{ top: 28, right: 8, bottom: 72, left: 8 }}>
                    <Pie
                      data={Object.entries(analysis.type_distribution)
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
                      {Object.entries(analysis.type_distribution)
                        .filter(([, v]) => v > 0)
                        .map(([name], i) => (
                          <Cell
                            key={name}
                            fill={['#1d9bf0', '#00ba7c', '#f7931a', '#e91e63', '#9c27b0', '#8b7355', '#00bcd4'][i % 7]}
                          />
                        ))}
                    </Pie>
                    <Tooltip />
                    <Legend layout="horizontal" verticalAlign="bottom" wrapperStyle={{ paddingTop: 4 }} formatter={(_, entry: { payload?: { name?: string; value?: number } }) => entry?.payload ? `${entry.payload.name ?? ''} ${entry.payload.value ?? ''}` : ''} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </div>
      )}

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Export:</span>
        <button
          type="button"
          className="btn"
          style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }}
          onClick={() => {
            const parts: string[] = []
            if (deck.commanders?.length) {
              parts.push('Commander')
              deck.commanders.forEach((c) => parts.push(`1 ${c}`))
              parts.push('')
            }
            parts.push('Deck')
            deck.mainboard.forEach(({ qty, card }) => parts.push(`${qty} ${card}`))
            if (deck.sideboard?.length) {
              parts.push('')
              parts.push('Sideboard')
              deck.sideboard.forEach(({ qty, card }) => parts.push(`${qty} ${card}`))
            }
            navigator.clipboard.writeText(parts.join('\n'))
          }}
        >
          Copy for MTGO
        </button>
        <button
          type="button"
          className="btn"
          style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }}
          onClick={() => {
            const parts: string[] = []
            if (deck.commanders?.length) {
              parts.push('Commander')
              deck.commanders.forEach((c) => parts.push(`1 ${c}`))
              parts.push('')
            }
            parts.push('Deck')
            deck.mainboard.forEach(({ qty, card }) => parts.push(`${qty} ${card}`))
            if (deck.sideboard?.length) {
              parts.push('')
              parts.push('Sideboard')
              deck.sideboard.forEach(({ qty, card }) => parts.push(`${qty} ${card}`))
            }
            navigator.clipboard.writeText(parts.join('\n'))
          }}
        >
          Copy for Moxfield
        </button>
      </div>

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <button
          type="button"
          className="btn"
          style={{ padding: '0.25rem 0.75rem', fontWeight: viewMode === 'list' ? 700 : 400 }}
          onClick={() => setViewMode('list')}
        >
          List
        </button>
        <button
          type="button"
          className="btn"
          style={{ padding: '0.25rem 0.75rem', fontWeight: viewMode === 'scryfall' ? 700 : 400 }}
          onClick={() => setViewMode('scryfall')}
        >
          Visual
        </button>
        {viewMode === 'list' && (
          <>
            <span style={{ marginLeft: '1rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}>Group by:</span>
            {(['type', 'cmc', 'color', 'none'] as GroupMode[]).map((m) => (
              <button
                key={m}
                type="button"
                className="btn"
                style={{
                  padding: '0.2rem 0.5rem',
                  fontSize: '0.8rem',
                  fontWeight: groupMode === m ? 700 : 400,
                }}
                onClick={() => setGroupMode(m)}
              >
                {m === 'type' ? 'Type' : m === 'cmc' ? 'Mana Value' : m === 'color' ? 'Color' : 'None'}
              </button>
            ))}
            <span style={{ marginLeft: '1rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}>Sort by:</span>
            {(['cmc', 'name'] as SortMode[]).map((m) => (
              <button
                key={m}
                type="button"
                className="btn"
                style={{
                  padding: '0.2rem 0.5rem',
                  fontSize: '0.8rem',
                  fontWeight: sortMode === m ? 700 : 400,
                }}
                onClick={() => setSortMode(m)}
              >
                {m === 'cmc' ? 'Mana value' : 'Name'}
              </button>
            ))}
          </>
        )}
      </div>

      {viewMode === 'scryfall' && (
        <div className="chart-container">
          <h3 style={{ margin: '0 0 1rem' }}>
            Deck ({(deck.commanders?.length ?? 0) + deck.mainboard.reduce((s, c) => s + c.qty, 0) + (deck.sideboard?.reduce((s, c) => s + c.qty, 0) ?? 0)} cards)
          </h3>
          {deck.commanders?.length ? (
            <CardGrid cards={deck.commanders.map((c) => ({ qty: 1, card: c }))} title="Commanders" embed />
          ) : null}
          <CardGrid cards={deck.mainboard} title={`Mainboard (${deck.mainboard.reduce((s, c) => s + c.qty, 0)} cards)`} embed />
          {deck.sideboard?.length ? (
            <CardGrid cards={deck.sideboard} title={`Sideboard (${deck.sideboard.reduce((s, c) => s + c.qty, 0)} cards)`} embed />
          ) : null}
        </div>
      )}

      {viewMode === 'list' && (
        <>
          <div style={{ marginBottom: '0.5rem', display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.5rem' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={showVsMetagame}
                onChange={(e) => setShowVsMetagame(e.target.checked)}
              />
              Highlight vs metagame (green = above avg, red = below avg)
            </label>
            {showVsMetagame && (
              <>
                <span style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>Date range:</span>
                <button
                  type="button"
                  className="btn"
                  style={{ padding: '0.2rem 0.4rem', fontSize: '0.8rem' }}
                  onClick={() => {
                    setMetagameDateFrom(null)
                    setMetagameDateTo(null)
                  }}
                >
                  All time
                </button>
                <button
                  type="button"
                  className="btn"
                  style={{ padding: '0.2rem 0.4rem', fontSize: '0.8rem' }}
                  onClick={() => maxDate && (setMetagameDateTo(maxDate), setMetagameDateFrom(firstDayOfYear(maxDate)))}
                >
                  This year
                </button>
                <button
                  type="button"
                  className="btn"
                  style={{ padding: '0.2rem 0.4rem', fontSize: '0.8rem' }}
                  onClick={() => maxDate && (setMetagameDateTo(maxDate), setMetagameDateFrom(dateMinusDays(maxDate, 183)))}
                >
                  6 months
                </button>
                <button
                  type="button"
                  className="btn"
                  style={{ padding: '0.2rem 0.4rem', fontSize: '0.8rem' }}
                  onClick={() => maxDate && (setMetagameDateTo(maxDate), setMetagameDateFrom(dateMinusDays(maxDate, 60)))}
                >
                  2 months
                </button>
                <button
                  type="button"
                  className="btn"
                  style={{ padding: '0.2rem 0.4rem', fontSize: '0.8rem' }}
                  onClick={() => maxDate && (setMetagameDateTo(maxDate), setMetagameDateFrom(dateMinusDays(maxDate, 30)))}
                >
                  Last month
                </button>
                <button
                  type="button"
                  className="btn"
                  style={{ padding: '0.2rem 0.4rem', fontSize: '0.8rem' }}
                  onClick={() => maxDate && (setMetagameDateTo(maxDate), setMetagameDateFrom(dateMinusDays(maxDate, 14)))}
                >
                  Last 2 weeks
                </button>
                <button
                  type="button"
                  className="btn"
                  style={{ padding: '0.2rem 0.4rem', fontSize: '0.8rem' }}
                  onClick={() => lastEventDate && (setMetagameDateFrom(lastEventDate), setMetagameDateTo(lastEventDate))}
                >
                  Last event
                </button>
              </>
            )}
          </div>

          <div className="chart-container" style={{ marginBottom: '1rem' }}>
            <h3 style={{ margin: '0 0 0.5rem' }}>
              Deck ({(deck.commanders?.length ?? 0) + deck.mainboard.reduce((s, c) => s + c.qty, 0) + (deck.sideboard?.reduce((s, c) => s + c.qty, 0) ?? 0)} cards)
            </h3>
            {deck.commanders?.length ? (
              <>
                <h4 style={{ margin: '0.75rem 0 0.35rem', fontSize: '0.95rem', color: 'var(--text-muted)' }}>Commanders</h4>
                <div className="deck-list" style={{ marginBottom: '0.5rem' }}>
                  {deck.commanders.map((c) => (
                    <div key={c} className="card-row">
                      <span className="qty">1</span>
                      <span>
                        <CardHover cardName={c} linkTo>{c}</CardHover>
                      </span>
                    </div>
                  ))}
                </div>
              </>
            ) : null}
            <h4 style={{ margin: '0.75rem 0 0.35rem', fontSize: '0.95rem', color: 'var(--text-muted)' }}>
              Mainboard ({deck.mainboard.reduce((s, c) => s + c.qty, 0)} cards)
            </h4>
            <CardListSection
              cards={deck.mainboard}
              grouped={getGroupedData(analysis, groupMode, 'main')}
              groupMode={groupMode}
              sortMode={sortMode}
              cardMeta={analysis?.card_meta}
              getCardHighlight={getCardHighlight}
              showVsMetagame={showVsMetagame}
              playRateByCard={playRateByCard}
            />
            {deck.sideboard?.length ? (
              <>
                <h4 style={{ margin: '1.25rem 0 0.35rem', fontSize: '0.95rem', color: 'var(--text-muted)' }}>
                  Sideboard ({deck.sideboard.reduce((s, c) => s + c.qty, 0)} cards)
                </h4>
                <CardListSection
                  cards={deck.sideboard}
                  grouped={getGroupedData(analysis, groupMode, 'side')}
                  groupMode={groupMode}
                  sortMode={sortMode}
                  cardMeta={analysis?.card_meta}
                  getCardHighlight={() => null}
                  showVsMetagame={false}
                  playRateByCard={{}}
                />
              </>
            ) : null}
          </div>
        </>
      )}

      {deck && (
        <div className="chart-container" style={{ marginTop: '1.5rem' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', marginBottom: '0.75rem' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.75rem' }}>
              <h3 style={{ margin: 0 }}>Similar Decks</h3>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.875rem' }}>
                <input
                  type="radio"
                  name="similar-scope"
                  checked={similarDecksSameEventOnly}
                  onChange={() => setSimilarDecksSameEventOnly(true)}
                  aria-label="Same event"
                />
                Same event
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.875rem' }}>
                <input
                  type="radio"
                  name="similar-scope"
                  checked={!similarDecksSameEventOnly}
                  onChange={() => setSimilarDecksSameEventOnly(false)}
                  aria-label="All events"
                />
                All events
              </label>
            </div>
            <button
              type="button"
              className="btn"
              disabled={compareSelectedIds.size === 0}
              onClick={() => {
                const ids = [deck.deck_id, ...compareSelectedIds]
                navigate(`/decks/compare?ids=${ids.join(',')}`)
              }}
            >
              {compareSelectedIds.size === 0
                ? 'Compare (select decks below)'
                : `Compare this deck with ${compareSelectedIds.size} selected`}
            </button>
          </div>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '0.75rem' }}>
            {similarDecksSameEventOnly
              ? 'Decks with high card overlap from the same event'
              : 'Decks with high card overlap across all events'}
          </p>
          {similarDecks.length > 0 ? (
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                {similarDecks.map((s) => {
                  const selected = compareSelectedIds.has(s.deck_id)
                  const atMax = compareSelectedIds.size >= MAX_COMPARE - 1 && !selected
                  return (
                    <li key={s.deck_id} style={{ padding: '0.5rem 0', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <input
                        type="checkbox"
                        id={`compare-${s.deck_id}`}
                        checked={selected}
                        disabled={atMax}
                        onChange={() => {
                          setCompareSelectedIds((prev) => {
                            const next = new Set(prev)
                            if (next.has(s.deck_id)) next.delete(s.deck_id)
                            else if (next.size < MAX_COMPARE - 1) next.add(s.deck_id)
                            return next
                          })
                        }}
                        aria-label={`Compare with ${s.name}`}
                      />
                      <label htmlFor={`compare-${s.deck_id}`} style={{ flex: 1, cursor: atMax ? 'default' : 'pointer', margin: 0 }}>
                        <Link to={`/decks/${s.deck_id}`} style={{ color: 'var(--accent)' }} onClick={(e) => e.stopPropagation()}>
                          {s.name}
                        </Link>
                        <span style={{ color: 'var(--text-muted)', marginLeft: '0.5rem' }}>
                          {s.player} — {s.event_name} ({s.date}) — {s.similarity}% overlap
                        </span>
                      </label>
                    </li>
                  )
                })}
              </ul>
          ) : (
            <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', margin: 0 }}>
              No similar decks found{similarDecksSameEventOnly ? ' in this event' : ''}.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
