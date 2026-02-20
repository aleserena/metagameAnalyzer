import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from 'recharts'
import { getDecks, getDeckCompare, getDeckAnalysis } from '../api'
import type { DeckAnalysis } from '../api'
import type { Deck } from '../types'
import CardHover from '../components/CardHover'

const MAX_DECKS = 4

export default function DeckCompare() {
  const [searchParams] = useSearchParams()
  const [selectedDecks, setSelectedDecks] = useState<Deck[]>([])
  const [compareData, setCompareData] = useState<Deck[] | null>(null)
  const [analyses, setAnalyses] = useState<Record<number, DeckAnalysis | null>>({})
  const [analysisLoading, setAnalysisLoading] = useState(false)
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
    setAnalyses({})
    getDeckCompare(selectedDecks.map((d) => d.deck_id))
      .then((r) => setCompareData(r.decks))
      .catch((e) => toast.error(e.message))
      .finally(() => setLoading(false))
  }

  // Fetch deck analyses when compare data is available
  useEffect(() => {
    if (!compareData || compareData.length < 2) {
      setAnalyses({})
      return
    }
    setAnalysisLoading(true)
    Promise.all(compareData.map((d) => getDeckAnalysis(d.deck_id)))
      .then((results) => {
        const next: Record<number, DeckAnalysis | null> = {}
        compareData.forEach((d, i) => {
          next[d.deck_id] = results[i] ?? null
        })
        setAnalyses(next)
      })
      .catch((e) => toast.error(e.message))
      .finally(() => setAnalysisLoading(false))
  }, [compareData])

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
        <>
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

          {analysisLoading && (
            <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '1rem' }}>
              Loading deck analysis…
            </p>
          )}

          {!analysisLoading && compareData.length >= 2 && compareData.every((d) => analyses[d.deck_id]) && (
            <div style={{ marginBottom: '1rem' }}>
              <h3 style={{ margin: '0 0 0.5rem' }}>Deck Analysis</h3>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '1rem' }}>
                Mana curve, color, lands, and card type distribution for each deck.
              </p>

              {/* Mana curve — one chart per deck */}
              <h4 style={{ margin: '1rem 0 0.5rem', fontSize: '0.95rem' }}>Mana Curve</h4>
              <div
                className="deck-analysis-grid"
                style={{
                  gridTemplateColumns: `repeat(${compareData.length}, minmax(0, 1fr))`,
                }}
              >
                {compareData.map((d) => {
                  const a = analyses[d.deck_id]!
                  const curveEntries = Object.entries(a.mana_curve).map(([cmc, count]) => ({ cmc: Number(cmc), count }))
                  const maxCmc = Math.max(0, ...curveEntries.map((x) => x.cmc))
                  const allCmc = Array.from({ length: maxCmc + 1 }, (_, i) => i)
                  const data = allCmc.map((cmc) => ({
                    cmc,
                    count: a.mana_curve[cmc] ?? 0,
                  }))
                  return (
                    <div key={d.deck_id} className="chart-container chart-container--flex">
                      <div style={{ marginBottom: '1.25rem' }}>
                        <h4 style={{ margin: 0, fontSize: '0.9rem' }}>{d.name}</h4>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{d.player}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{d.event_name} ({d.date})</div>
                      </div>
                      <ResponsiveContainer width="100%" height={180}>
                        <BarChart data={data} margin={{ top: 10, right: 16, left: 36, bottom: 24 }}>
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
                  )
                })}
              </div>

              {/* Color distribution */}
              <h4 style={{ margin: '1rem 0 0.5rem', fontSize: '0.95rem' }}>Color Distribution</h4>
              {(() => {
                const colorHeights = compareData.map((d) => {
                  const a = analyses[d.deck_id]!
                  const n = [
                    a.color_distribution.W, a.color_distribution.U, a.color_distribution.B,
                    a.color_distribution.R, a.color_distribution.G, a.color_distribution.C,
                  ].filter((v) => v != null && v > 0).length
                  return {
                    height: n >= 5 ? Math.max(200, 160 + n * 24) : 200,
                    bottom: n >= 5 ? Math.max(58, 48 + n * 10) : 58,
                  }
                })
                const maxColorHeight = Math.max(200, ...colorHeights.map((h) => h.height))
                const maxColorBottom = Math.max(58, ...colorHeights.map((h) => h.bottom))
                return (
                  <div
                    className="deck-analysis-grid"
                    style={{
                      gridTemplateColumns: `repeat(${compareData.length}, minmax(0, 1fr))`,
                    }}
                  >
                    {compareData.map((d) => {
                      const a = analyses[d.deck_id]!
                      const colorData = [
                        { name: 'White', value: a.color_distribution.W || 0, color: '#fff9e6' },
                        { name: 'Blue', value: a.color_distribution.U || 0, color: '#0e4d92' },
                        { name: 'Black', value: a.color_distribution.B || 0, color: '#8b8b8b' },
                        { name: 'Red', value: a.color_distribution.R || 0, color: '#c41e3a' },
                        { name: 'Green', value: a.color_distribution.G || 0, color: '#007a33' },
                        { name: 'Colorless', value: a.color_distribution.C || 0, color: '#b0b0b0' },
                      ].filter((x) => x.value > 0)
                      return (
                        <div key={d.deck_id} className="chart-container chart-container--flex">
                          <div style={{ marginBottom: '1.25rem' }}>
                            <h4 style={{ margin: 0, fontSize: '0.9rem' }}>{d.name}</h4>
                            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{d.player}</div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{d.event_name} ({d.date})</div>
                          </div>
                          <ResponsiveContainer width="100%" height={maxColorHeight}>
                            <PieChart margin={{ top: 28, right: 8, bottom: maxColorBottom, left: 8 }}>
                          <Pie
                            data={colorData}
                            label={false}
                            dataKey="value"
                            nameKey="name"
                            cx="50%"
                            cy="50%"
                            outerRadius={58}
                          >
                            {colorData.map((c) => (
                              <Cell key={c.name} fill={c.color} />
                            ))}
                          </Pie>
                          <Tooltip />
                          <Legend
                            layout="horizontal"
                            verticalAlign="bottom"
                            wrapperStyle={{ paddingTop: 4 }}
                            formatter={(_, entry: { payload?: { name: string; value: number } }) =>
                              entry.payload ? `${entry.payload.name} ${entry.payload.value}%` : ''
                            }
                          />
                        </PieChart>
                          </ResponsiveContainer>
                        </div>
                      )
                    })}
                  </div>
                )
              })()}

              {/* Lands distribution */}
              <h4 style={{ margin: '1rem 0 0.5rem', fontSize: '0.95rem' }}>Lands Distribution</h4>
              <div
                className="deck-analysis-grid"
                style={{
                  gridTemplateColumns: `repeat(${compareData.length}, minmax(0, 1fr))`,
                }}
              >
                {compareData.map((d) => {
                  const a = analyses[d.deck_id]!
                  const landData = [
                    { name: 'Lands', value: a.lands_distribution.lands, color: '#8b7355' },
                    { name: 'Non-Lands', value: a.lands_distribution.nonlands, color: '#1d9bf0' },
                  ].filter((x) => x.value > 0)
                  const total = a.lands_distribution.lands + a.lands_distribution.nonlands
                  return (
                    <div key={d.deck_id} className="chart-container chart-container--flex">
                      <div style={{ marginBottom: '1.25rem' }}>
                        <h4 style={{ margin: 0, fontSize: '0.9rem' }}>{d.name}</h4>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{d.player}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{d.event_name} ({d.date})</div>
                      </div>
                      <ResponsiveContainer width="100%" height={200}>
                        <PieChart margin={{ top: 28, right: 8, bottom: 58, left: 8 }}>
                          <Pie
                            data={landData}
                            label={false}
                            dataKey="value"
                            nameKey="name"
                            cx="50%"
                            cy="50%"
                            outerRadius={58}
                          >
                            {landData.map((c) => (
                              <Cell key={c.name} fill={c.color} />
                            ))}
                          </Pie>
                          <Tooltip />
                          <Legend
                            layout="horizontal"
                            verticalAlign="bottom"
                            wrapperStyle={{ paddingTop: 4 }}
                            formatter={(_, entry: { payload?: { name: string; value: number } }) => {
                              const p = entry.payload
                              if (!p) return ''
                              const pct = total ? Math.round((100 * p.value) / total) : 0
                              return `${p.name} ${p.value} (${pct}%)`
                            }}
                          />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                  )
                })}
              </div>

              {/* Card type distribution — only if at least one deck has it */}
              {compareData.some((d) => analyses[d.deck_id]?.type_distribution && Object.keys(analyses[d.deck_id]!.type_distribution!).length > 0) && (
                <>
                  <h4 style={{ margin: '1rem 0 0.5rem', fontSize: '0.95rem' }}>Card Type Distribution</h4>
                  {(() => {
                    const typeHeights = compareData.map((d) => {
                      const typeDist = analyses[d.deck_id]!.type_distribution ?? {}
                      const n = Object.entries(typeDist).filter(([, v]) => v > 0).length
                      return {
                        height: n >= 5 ? Math.max(260, 200 + n * 36) : 220,
                        bottom: n >= 5 ? Math.max(72, 56 + n * 14) : 72,
                      }
                    })
                    const maxTypeHeight = Math.max(220, ...typeHeights.map((h) => h.height))
                    const maxTypeBottom = Math.max(72, ...typeHeights.map((h) => h.bottom))
                    return (
                      <div
                        className="deck-analysis-grid"
                        style={{
                          gridTemplateColumns: `repeat(${compareData.length}, minmax(0, 1fr))`,
                        }}
                      >
                        {compareData.map((d) => {
                          const a = analyses[d.deck_id]!
                          const typeDist = a.type_distribution ?? {}
                          const typeData = Object.entries(typeDist)
                            .filter(([, v]) => v > 0)
                            .map(([name, value], i) => ({
                              name,
                              value,
                              color: ['#1d9bf0', '#00ba7c', '#f7931a', '#e91e63', '#9c27b0', '#8b7355', '#00bcd4'][i % 7],
                            }))
                          return (
                            <div key={d.deck_id} className="chart-container chart-container--flex">
                              <div style={{ marginBottom: '1.25rem' }}>
                                <h4 style={{ margin: 0, fontSize: '0.9rem' }}>{d.name}</h4>
                                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{d.player}</div>
                                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{d.event_name} ({d.date})</div>
                              </div>
                              <ResponsiveContainer width="100%" height={maxTypeHeight}>
                                <PieChart margin={{ top: 36, right: 8, bottom: maxTypeBottom, left: 8 }}>
                              <Pie
                                data={typeData}
                                dataKey="value"
                                nameKey="name"
                                cx="50%"
                                cy="50%"
                                outerRadius={54}
                                label={false}
                              >
                                {typeData.map((c) => (
                                  <Cell key={c.name} fill={c.color} />
                                ))}
                              </Pie>
                              <Tooltip />
                              <Legend
                                layout="horizontal"
                                verticalAlign="bottom"
                                wrapperStyle={{ paddingTop: 4 }}
                                formatter={(_, entry: { payload?: { name: string; value: number } }) =>
                                  entry.payload ? `${entry.payload.name} ${entry.payload.value}` : ''
                                }
                              />
                            </PieChart>
                                </ResponsiveContainer>
                              </div>
                            )
                          })}
                        </div>
                      )
                    })()}
                </>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
