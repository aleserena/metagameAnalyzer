import { useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { getDeck, getMetagame, getDeckAnalysis, getDateRange, getSimilarDecks, deleteDeck, getCardLookup, createEventUploadLinks } from '../api'
import { useAuth } from '../contexts/AuthContext'
import type { Deck, MetagameReport, SimilarDeck } from '../types'
import type { DeckAnalysis, CardLookupResult } from '../api'
import CardGrid from '../components/CardGrid'
import CardHover from '../components/CardHover'
import ManaSymbols from '../components/ManaSymbols'
import CardListSection, { getGroupedData, type GroupMode, type SortMode } from '../components/deck/CardListSection'
import DeckEditSection from '../components/deck/DeckEditSection'
import DeckAnalysisCharts from '../components/deck/DeckAnalysisCharts'
import { WUBRG_ORDER } from '../lib/deckUtils'
import { getDateRangeFromPreset, reportError } from '../utils'
import type { DatePreset } from '../utils'

type ViewMode = 'list' | 'scryfall'
const SAMPLE_HAND_SIZE = 7

/** Draw up to `count` random cards from mainboard (each card weighted by qty). */
function drawSampleHand(mainboard: { qty: number; card: string }[], count: number): string[] {
  const pool = mainboard.flatMap(({ qty, card }) => Array(qty).fill(card) as string[])
  if (pool.length === 0) return []
  const n = Math.min(count, pool.length)
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [pool[i], pool[j]] = [pool[j]!, pool[i]!]
  }
  return pool.slice(0, n)
}

export default function DeckDetail() {
  const { deckId } = useParams<{ deckId: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
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
  const [deleting, setDeleting] = useState(false)
  const [generatingUpdateLink, setGeneratingUpdateLink] = useState(false)
  const [commanderLookup, setCommanderLookup] = useState<Record<string, CardLookupResult> | null>(null)
  const [sampleHand, setSampleHand] = useState<string[]>([])
  const [handLookup, setHandLookup] = useState<Record<string, CardLookupResult>>({})
  const MAX_COMPARE = 4

  useEffect(() => {
    const main = deck?.mainboard ?? []
    setSampleHand(drawSampleHand(main, SAMPLE_HAND_SIZE))
  }, [deck?.mainboard])

  useEffect(() => {
    if (sampleHand.length === 0) {
      setHandLookup({})
      return
    }
    getCardLookup([...new Set(sampleHand)])
      .then(setHandLookup)
      .catch(() => setHandLookup({}))
  }, [sampleHand.join(',')])

  const drawNewHand = () => {
    const main = deck?.mainboard ?? []
    setSampleHand(drawSampleHand(main, SAMPLE_HAND_SIZE))
  }

  useEffect(() => {
    const commanders = deck?.commanders?.filter(Boolean) ?? []
    if (commanders.length === 0) {
      setCommanderLookup(null)
      return
    }
    getCardLookup(commanders)
      .then(setCommanderLookup)
      .catch(() => setCommanderLookup({}))
  }, [deck?.commanders])

  const deckManaCost = useMemo(() => {
    const colors: string[] = []
    if (commanderLookup && deck?.commanders?.length) {
      const set = new Set<string>()
      for (const name of deck.commanders) {
        const entry = commanderLookup[name]
        if (entry?.error) continue
        for (const c of entry?.color_identity ?? entry?.colors ?? []) {
          if ((WUBRG_ORDER as readonly string[]).includes(c)) set.add(c)
        }
      }
      colors.push(...WUBRG_ORDER.filter((c) => set.has(c)))
    } else if (analysis?.color_distribution) {
      colors.push(...WUBRG_ORDER.filter((c) => (analysis.color_distribution[c] ?? 0) > 0))
    }
    return colors.length ? `{${colors.join('}{')}}` : ''
  }, [deck?.commanders, commanderLookup, analysis?.color_distribution])

  // Exclude 100% overlap (duplicate) decks from the similar list
  const displayedSimilarDecks = useMemo(
    () => similarDecks.filter((s) => s.similarity < 100),
    [similarDecks]
  )

  useEffect(() => {
    if (!deckId) return
    getDeck(parseInt(deckId, 10))
      .then(setDeck)
      .catch((e) => {
        setError(e.message)
        toast.error(reportError(e))
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

      <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
        {deck.name}
        {deckManaCost ? <ManaSymbols manaCost={deckManaCost} size={28} /> : null}
      </h1>

      {deck.duplicate_info && deck.mainboard && deck.mainboard.length > 0 && (
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
              <Link to={`/players/${deck.player_id != null ? deck.player_id : encodeURIComponent(deck.player)}`} style={{ color: 'var(--accent)' }}>
                {deck.player}
              </Link>
            </div>
          </div>
          <div>
            <div className="label">Event</div>
            <div>
              <Link to={deck.event_id ? `/events/${encodeURIComponent(String(deck.event_id))}` : '/events'} style={{ color: 'var(--accent)' }}>
                {deck.event_name || 'Unnamed'}
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
            <div>
              {deck.archetype ? (
                <Link
                  to={`/archetypes/${encodeURIComponent(deck.archetype)}`}
                  style={{ color: 'var(--accent)' }}
                >
                  {deck.archetype}
                </Link>
              ) : (
                '-'
              )}
            </div>
          </div>
        </div>
      </div>

      <DeckEditSection
        deck={deck}
        onUpdate={setDeck}
        onCardsSaved={() => getDeckAnalysis(deck.deck_id).then(setAnalysis).catch(() => setAnalysis(null))}
      />

      {user === 'admin' && deck && (
        <>
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ margin: '0 0 0.75rem' }}>Update link</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '0.75rem' }}>
            Create a one-time link so the player can update this deck (name, rank, deck list) without logging in.
          </p>
          <button
            type="button"
            className="btn"
            disabled={generatingUpdateLink || !deck.event_id}
            onClick={() => {
              if (!deck.event_id) return
              setGeneratingUpdateLink(true)
              createEventUploadLinks(deck.event_id, { deck_id: deck.deck_id })
                .then((res) => {
                  if (res.links.length > 0) {
                    const url = res.links[0].url || `${typeof window !== 'undefined' ? window.location.origin : ''}/upload/${res.links[0].token}`
                    window.navigator.clipboard.writeText(url).then(
                      () => toast.success('Update link copied to clipboard'),
                      () => toast.success('Update link generated')
                    )
                  }
                })
                .catch((e) => toast.error(e?.message || 'Failed to create link'))
                .finally(() => setGeneratingUpdateLink(false))
            }}
          >
            {generatingUpdateLink ? 'Generating…' : 'Copy update link'}
          </button>
        </div>
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ margin: '0 0 0.75rem' }}>Danger zone</h3>
          <button
            type="button"
            className="btn"
            style={{ color: 'var(--danger, #c00)' }}
            disabled={deleting}
            onClick={() => {
              if (!window.confirm(`Delete deck "${deck.name}"? This cannot be undone.`)) return
              setDeleting(true)
              deleteDeck(deck.deck_id)
                .then(() => {
                  toast.success('Deck deleted')
                  navigate(deck.event_id ? `/events/${deck.event_id}` : '/decks')
                })
                .catch((e) => toast.error(reportError(e)))
                .finally(() => setDeleting(false))
            }}
          >
            {deleting ? 'Deleting…' : 'Delete deck'}
          </button>
        </div>
        </>
      )}

      {analysis && <DeckAnalysisCharts analysis={analysis} />}

      <div className="toolbar toolbar--wrap-on-mobile" style={{ marginBottom: '1rem', gap: '0.5rem', alignItems: 'center' }}>
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
            navigator.clipboard.writeText(parts.join('\n')).then(
              () => toast.success('Deck copied to clipboard'),
              () => toast.error('Failed to copy')
            )
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
            navigator.clipboard.writeText(parts.join('\n')).then(
              () => toast.success('Deck copied to clipboard'),
              () => toast.error('Failed to copy')
            )
          }}
        >
          Copy for Moxfield
        </button>
      </div>

      <div className="toolbar toolbar--wrap-on-mobile" style={{ marginBottom: '1rem', gap: '0.5rem', alignItems: 'center' }}>
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
          <div className="toolbar toolbar--stack-on-mobile pill-group" style={{ marginBottom: '0.5rem', gap: '0.5rem', alignItems: 'center' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={showVsMetagame}
                onChange={(e) => setShowVsMetagame(e.target.checked)}
              />
              Highlight vs metagame (green = above avg, red = below avg)
            </label>
            {showVsMetagame && (() => {
              const applyPreset = (preset: DatePreset) => {
                const { dateFrom, dateTo } = getDateRangeFromPreset(maxDate, lastEventDate, preset)
                setMetagameDateFrom(dateFrom)
                setMetagameDateTo(dateTo)
              }
              return (
                <>
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>Date range:</span>
                  <button type="button" className="btn" style={{ padding: '0.2rem 0.4rem', fontSize: '0.8rem' }} onClick={() => applyPreset('all')}>All time</button>
                  <button type="button" className="btn" style={{ padding: '0.2rem 0.4rem', fontSize: '0.8rem' }} onClick={() => applyPreset('thisYear')}>This year</button>
                  <button type="button" className="btn" style={{ padding: '0.2rem 0.4rem', fontSize: '0.8rem' }} onClick={() => applyPreset('6months')}>6 months</button>
                  <button type="button" className="btn" style={{ padding: '0.2rem 0.4rem', fontSize: '0.8rem' }} onClick={() => applyPreset('2months')}>2 months</button>
                  <button type="button" className="btn" style={{ padding: '0.2rem 0.4rem', fontSize: '0.8rem' }} onClick={() => applyPreset('month')}>Last month</button>
                  <button type="button" className="btn" style={{ padding: '0.2rem 0.4rem', fontSize: '0.8rem' }} onClick={() => applyPreset('2weeks')}>Last 2 weeks</button>
                  <button type="button" className="btn" style={{ padding: '0.2rem 0.4rem', fontSize: '0.8rem' }} onClick={() => applyPreset('lastEvent')}>Last event</button>
                </>
              )
            })()}
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

      {deck.mainboard && deck.mainboard.length > 0 && (
        <div className="chart-container" style={{ marginBottom: '1.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
            <h3 style={{ margin: 0 }}>Sample hand</h3>
            <button type="button" className="btn" onClick={drawNewHand}>
              New hand
            </button>
          </div>
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: '0.5rem',
              alignItems: 'flex-start',
            }}
          >
            {sampleHand.map((cardName, i) => {
              const data = handLookup[cardName]
              const img = data?.error ? null : (data?.image_uris?.normal ?? data?.image_uris?.small)
              return (
                <Link
                  key={`${cardName}-${i}`}
                  to={`/decks?card=${encodeURIComponent(cardName)}`}
                  style={{
                    display: 'block',
                    width: 140,
                    flexShrink: 0,
                    borderRadius: 4,
                    overflow: 'hidden',
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border)',
                    textDecoration: 'none',
                    color: 'inherit',
                  }}
                  title={cardName}
                >
                  {img ? (
                    <img
                      src={img}
                      alt={cardName}
                      style={{ width: '100%', height: 'auto', display: 'block', verticalAlign: 'middle' }}
                    />
                  ) : (
                    <div
                      style={{
                        aspectRatio: '223/311',
                        padding: '0.5rem',
                        fontSize: '0.75rem',
                        color: 'var(--text-muted)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        textAlign: 'center',
                      }}
                    >
                      {cardName}
                    </div>
                  )}
                </Link>
              )
            })}
          </div>
        </div>
      )}

      {deck && (
        <div className="chart-container" style={{ marginTop: '1.5rem' }}>
          <div className="toolbar toolbar--stack-on-mobile" style={{ justifyContent: 'space-between', marginBottom: '0.75rem', gap: '0.75rem' }}>
            <div className="toolbar pill-group" style={{ gap: '0.75rem', alignItems: 'center' }}>
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
          {displayedSimilarDecks.length > 0 ? (
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                {displayedSimilarDecks.map((s) => {
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
