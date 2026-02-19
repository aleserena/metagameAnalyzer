import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { getDecks, getDeckCompare } from '../api'
import type { Deck } from '../types'
import CardHover from '../components/CardHover'

const MAX_DECKS = 4

export default function DeckCompare() {
  const [searchParams] = useSearchParams()
  const [selectedDecks, setSelectedDecks] = useState<Deck[]>([])
  const [compareData, setCompareData] = useState<Deck[] | null>(null)
  const [search, setSearch] = useState('')
  const [searchResults, setSearchResults] = useState<Deck[]>([])
  const [loading, setLoading] = useState(false)
  const [initDone, setInitDone] = useState(false)

  // Auto-load from ?ids= query param
  useEffect(() => {
    if (initDone) return
    setInitDone(true)
    const idsParam = searchParams.get('ids')
    if (!idsParam) return
    const ids = idsParam.split(',').map(Number).filter(Boolean)
    if (ids.length < 2) return
    setLoading(true)
    getDeckCompare(ids)
      .then((r) => {
        setSelectedDecks(r.decks)
        setCompareData(r.decks)
      })
      .catch((e) => toast.error(e.message))
      .finally(() => setLoading(false))
  }, [searchParams, initDone])

  useEffect(() => {
    if (!search.trim()) {
      setSearchResults([])
      return
    }
    const t = setTimeout(() => {
      getDecks({ deck_name: search, limit: 20 })
        .then((r) => setSearchResults(r.decks))
        .catch(() => setSearchResults([]))
    }, 300)
    return () => clearTimeout(t)
  }, [search])

  const addDeck = (d: Deck) => {
    if (selectedDecks.some((x) => x.deck_id === d.deck_id)) return
    if (selectedDecks.length >= MAX_DECKS) return
    setSelectedDecks((prev) => [...prev, d])
    setSearch('')
    setSearchResults([])
  }

  const removeDeck = (deckId: number) => {
    setSelectedDecks((prev) => prev.filter((d) => d.deck_id !== deckId))
    setCompareData(null)
  }

  const runCompare = () => {
    if (selectedDecks.length < 2) return
    setLoading(true)
    getDeckCompare(selectedDecks.map((d) => d.deck_id))
      .then((r) => setCompareData(r.decks))
      .catch((e) => toast.error(e.message))
      .finally(() => setLoading(false))
  }

  const allCards = compareData
    ? [...new Set(compareData.flatMap((d) => d.mainboard.map((c) => c.card)))]
    : []
  const cardInDeck = (card: string, deck: Deck) =>
    deck.mainboard.some((c) => c.card === card)
  const cardQtyInDeck = (card: string, deck: Deck) =>
    deck.mainboard.find((c) => c.card === card)?.qty ?? 0

  const UNIQUE_COLORS = [
    'rgba(29, 155, 240, 0.25)',
    'rgba(247, 147, 26, 0.25)',
    'rgba(156, 39, 176, 0.25)',
    'rgba(0, 188, 212, 0.25)',
  ]
  const getCellBg = (card: string, deck: Deck, deckIndex: number) => {
    const inDecks = compareData!.filter((d) => cardInDeck(card, d))
    const isCommon = inDecks.length === compareData!.length
    if (!cardInDeck(card, deck)) return undefined
    if (isCommon) return 'rgba(0, 186, 124, 0.1)'
    if (inDecks.length === 1 && inDecks[0].deck_id === deck.deck_id) {
      return UNIQUE_COLORS[deckIndex % UNIQUE_COLORS.length]
    }
    return undefined
  }

  return (
    <div>
      <h1 className="page-title">Compare Decks</h1>

      <div style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', flexWrap: 'wrap' }}>
          <input
            type="text"
            placeholder="Search deck name..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="form-group"
            style={{ flex: 1, minWidth: 200 }}
          />
        </div>
        {searchResults.length > 0 && (
          <div
            style={{
              border: '1px solid var(--border)',
              borderRadius: 4,
              maxHeight: 200,
              overflowY: 'auto',
              marginBottom: '0.5rem',
            }}
          >
            {searchResults.map((d) => (
              <div
                key={d.deck_id}
                className="clickable"
                style={{ padding: '0.5rem 1rem', borderBottom: '1px solid var(--border)' }}
                onClick={() => addDeck(d)}
              >
                {d.name} — {d.player} ({d.date})
              </div>
            ))}
          </div>
        )}

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          {selectedDecks.map((d) => (
            <span
              key={d.deck_id}
              style={{
                padding: '0.25rem 0.5rem',
                background: 'var(--bg-card)',
                borderRadius: 4,
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
              }}
            >
              {d.name}
              <button
                type="button"
                onClick={() => removeDeck(d.deck_id)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1.2rem' }}
              >
                ×
              </button>
            </span>
          ))}
          {selectedDecks.length < MAX_DECKS && (
            <span style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
              Select 2–{MAX_DECKS} decks
            </span>
          )}
        </div>

        <button
          className="btn"
          style={{ marginTop: '1rem' }}
          onClick={runCompare}
          disabled={selectedDecks.length < 2 || loading}
        >
          {loading ? 'Loading...' : 'Compare'}
        </button>
      </div>

      {compareData && compareData.length >= 2 && (
        <div className="chart-container">
          <h3 style={{ margin: '0 0 1rem' }}>Card Comparison</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '1rem' }}>
            Green = in all decks. Colored cells = unique to that deck. &quot;(unique)&quot; = only in one deck.
          </p>
          <div className="table-wrap" style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th>Card</th>
                  {compareData.map((d) => (
                    <th key={d.deck_id} style={{ minWidth: 140 }}>
                      <div>{d.name}</div>
                      <div style={{ fontWeight: 'normal', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                        {d.player}
                      </div>
                      <div style={{ fontWeight: 'normal', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        {d.event_name} ({d.date})
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {allCards.sort().map((card) => {
                  const inDecks = compareData.filter((d) => cardInDeck(card, d))
                  const isCommon = inDecks.length === compareData.length
                  const isUnique = inDecks.length === 1
                  return (
                    <tr
                      key={card}
                      style={{
                        background: isCommon ? 'rgba(0, 186, 124, 0.08)' : undefined,
                      }}
                    >
                      <td>
                        <CardHover cardName={card} linkTo>{card}</CardHover>
                        {isUnique && (
                          <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginLeft: 4 }}>
                            (unique)
                          </span>
                        )}
                      </td>
                      {compareData.map((d, i) => (
                        <td key={d.deck_id} style={{ background: getCellBg(card, d, i) }}>
                          {cardInDeck(card, d) ? cardQtyInDeck(card, d) : '—'}
                        </td>
                      ))}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
