import { useEffect, useMemo, useRef, useState } from 'react'
import { getMatchupsSummary, getMatchupsPlayersSummary } from '../api'
import EventSelector from '../components/EventSelector'
import FiltersPanel from '../components/FiltersPanel'
import { useEventMetadata } from '../hooks/useEventMetadata'
import Skeleton from '../components/Skeleton'
import toast from 'react-hot-toast'
import { reportError } from '../utils'

const DROPDOWN_MAX_HEIGHT = 240
const DROPDOWN_GAP = 4

type ViewMode = 'list' | 'matrix'
type DataMode = 'archetypes' | 'players'

const TOOLTIP_ESTIMATE = { width: 270, height: 100 }
const TOOLTIP_PAD = 12

/** Position tooltip so it stays inside the viewport (e.g. show above for bottom cells). */
function getTooltipPosition(rect: DOMRect): { left: number; top: number; transform: string } {
  const vw = window.innerWidth
  const vh = window.innerHeight
  const halfW = TOOLTIP_ESTIMATE.width / 2
  const centerX = rect.left + rect.width / 2
  const left = Math.max(TOOLTIP_PAD + halfW, Math.min(vw - TOOLTIP_PAD - halfW, centerX))
  const showBelow = rect.bottom + 8 + TOOLTIP_ESTIMATE.height <= vh - TOOLTIP_PAD
  if (showBelow) {
    return { left, top: rect.bottom, transform: 'translate(-50%, 8px)' }
  }
  return { left, top: rect.top, transform: 'translate(-50%, calc(-100% - 8px))' }
}

/** Win rate 0–100 → heatmap color (red → yellow → green) with opacity for readability. */
function heatmapColor(pct: number): string {
  const t = Math.max(0, Math.min(100, pct)) / 100
  let r: number
  let g: number
  if (t <= 0.5) {
    r = 220
    g = Math.round(80 + (220 - 80) * (t * 2))
  } else {
    r = Math.round(220 - (220 - 80) * ((t - 0.5) * 2))
    g = 220
  }
  const b = 80
  return `rgba(${r},${g},${b},0.35)`
}

export default function Matchups() {
  const { events, maxDate, lastEventDate, error: eventMetadataError } = useEventMetadata()
  const [summary, setSummary] = useState<Awaited<ReturnType<typeof getMatchupsSummary>> | null>(null)
  const [playersSummary, setPlayersSummary] = useState<Awaited<ReturnType<typeof getMatchupsPlayersSummary>> | null>(null)
  const [loading, setLoading] = useState(true)
  const [playersLoading, setPlayersLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [playersError, setPlayersError] = useState<string | null>(null)
  const [formatId, setFormatId] = useState('')
  const [eventIds, setEventIds] = useState<(number | string)[]>([])
  const [dataMode, setDataMode] = useState<DataMode>('archetypes')
  const [selectedArchetypes, setSelectedArchetypes] = useState<string[]>([])
  const [archetypeOptions, setArchetypeOptions] = useState<string[]>([])
  const [archetypeOpen, setArchetypeOpen] = useState(false)
  const [selectedPlayers, setSelectedPlayers] = useState<string[]>([])
  const [playerOptions, setPlayerOptions] = useState<string[]>([])
  const [playerOpen, setPlayerOpen] = useState(false)
  const [viewMode, setViewMode] = useState<ViewMode>('matrix')
  const [sortByWinRate, setSortByWinRate] = useState(false)
  const archetypeRef = useRef<HTMLDivElement>(null)
  const archetypeButtonRef = useRef<HTMLButtonElement>(null)
  const playerRef = useRef<HTMLDivElement>(null)
  const playerButtonRef = useRef<HTMLButtonElement>(null)
  const [archetypeFlipAbove, setArchetypeFlipAbove] = useState(false)
  const [archetypeMaxHeight, setArchetypeMaxHeight] = useState(DROPDOWN_MAX_HEIGHT)
  const [playerFlipAbove, setPlayerFlipAbove] = useState(false)
  const [playerMaxHeight, setPlayerMaxHeight] = useState(DROPDOWN_MAX_HEIGHT)
  const [hoveredCell, setHoveredCell] = useState<{
    archetype: string
    opponent: string
    rect: DOMRect
  } | null>(null)
  const [hoveredPlayerCell, setHoveredPlayerCell] = useState<{
    player: string
    opponent: string
    rect: DOMRect
  } | null>(null)

  useEffect(() => {
    if (eventMetadataError) toast.error(reportError(new Error(eventMetadataError)))
  }, [eventMetadataError])

  useEffect(() => {
    if (dataMode !== 'archetypes') return
    setLoading(true)
    setError(null)
    getMatchupsSummary({
      format_id: formatId || undefined,
      event_ids: eventIds.length ? eventIds.map(String).join(',') : undefined,
      archetype: selectedArchetypes.length ? selectedArchetypes : undefined,
    })
      .then((s) => {
        setSummary(s)
        setArchetypeOptions((prev) => {
          const fromSummary = s?.archetypes ?? []
          if (fromSummary.length === 0) return prev
          return [...new Set([...prev, ...fromSummary])].sort()
        })
      })
      .catch((e) => {
        setError(reportError(e))
        setSummary(null)
      })
      .finally(() => setLoading(false))
  }, [dataMode, formatId, eventIds, selectedArchetypes])

  useEffect(() => {
    if (dataMode !== 'players') return
    setPlayersLoading(true)
    setPlayersError(null)
    getMatchupsPlayersSummary({
      format_id: formatId || undefined,
      event_ids: eventIds.length ? eventIds.map(String).join(',') : undefined,
      player: selectedPlayers.length ? selectedPlayers : undefined,
    })
      .then((s) => {
        setPlayersSummary(s)
        setPlayerOptions((prev) => {
          const fromSummary = s?.players ?? []
          if (fromSummary.length === 0) return prev
          return [...new Set([...prev, ...fromSummary])].sort()
        })
      })
      .catch((e) => {
        setPlayersError(reportError(e))
        setPlayersSummary(null)
      })
      .finally(() => setPlayersLoading(false))
  }, [dataMode, formatId, eventIds, selectedPlayers])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (archetypeRef.current && !archetypeRef.current.contains(e.target as Node)) setArchetypeOpen(false)
      if (playerRef.current && !playerRef.current.contains(e.target as Node)) setPlayerOpen(false)
    }
    if (archetypeOpen || playerOpen) document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [archetypeOpen, playerOpen])

  useEffect(() => {
    if (!archetypeOpen || !archetypeButtonRef.current) return
    const rect = archetypeButtonRef.current.getBoundingClientRect()
    const spaceBelow = window.innerHeight - rect.bottom - DROPDOWN_GAP
    const spaceAbove = rect.top - DROPDOWN_GAP
    const shouldFlip = spaceBelow < DROPDOWN_MAX_HEIGHT && spaceAbove > spaceBelow
    setArchetypeFlipAbove(shouldFlip)
    const available = shouldFlip ? spaceAbove : spaceBelow
    setArchetypeMaxHeight(Math.min(DROPDOWN_MAX_HEIGHT, Math.max(100, available)))
  }, [archetypeOpen])

  useEffect(() => {
    if (!playerOpen || !playerButtonRef.current) return
    const rect = playerButtonRef.current.getBoundingClientRect()
    const spaceBelow = window.innerHeight - rect.bottom - DROPDOWN_GAP
    const spaceAbove = rect.top - DROPDOWN_GAP
    const shouldFlip = spaceBelow < DROPDOWN_MAX_HEIGHT && spaceAbove > spaceBelow
    setPlayerFlipAbove(shouldFlip)
    const available = shouldFlip ? spaceAbove : spaceBelow
    setPlayerMaxHeight(Math.min(DROPDOWN_MAX_HEIGHT, Math.max(100, available)))
  }, [playerOpen])

  const toggleArchetype = (name: string) => {
    setSelectedArchetypes((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return [...next]
    })
  }

  const togglePlayer = (name: string) => {
    setSelectedPlayers((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return [...next]
    })
  }

  const matchupsByPair = useMemo(() => {
    const m = new Map<string, (Awaited<ReturnType<typeof getMatchupsSummary>>['list'][number])>()
    if (!summary) return m
    for (const row of summary.list) {
      m.set(`${row.archetype}|||${row.opponent_archetype}`, row)
    }
    return m
  }, [summary])

  const playersByPair = useMemo(() => {
    const m = new Map<string, (Awaited<ReturnType<typeof getMatchupsPlayersSummary>>['players_list'][number])>()
    if (!playersSummary) return m
    for (const row of playersSummary.players_list) {
      m.set(`${row.player}|||${row.opponent_player}`, row)
    }
    return m
  }, [playersSummary])

  const archetypeOverallWinRate = useMemo(() => {
    const map = new Map<string, number>()
    if (!summary) return map
    const agg = new Map<string, { wins: number; draws: number; matches: number }>()
    for (const row of summary.list) {
      const a = (row.archetype || '').trim()
      if (!a) continue
      const prev = agg.get(a) ?? { wins: 0, draws: 0, matches: 0 }
      prev.wins += row.wins
      prev.draws += row.draws
      prev.matches += row.matches
      agg.set(a, prev)
    }
    for (const [a, v] of agg.entries()) {
      const denom = v.matches || 0
      const wr = denom ? (v.wins + 0.5 * v.draws) / denom : 0
      map.set(a, wr)
    }
    return map
  }, [summary])

  const playersOverallWinRate = useMemo(() => {
    const map = new Map<string, number>()
    if (!playersSummary) return map
    const agg = new Map<string, { wins: number; draws: number; matches: number }>()
    for (const row of playersSummary.players_list) {
      const p = (row.player || '').trim()
      if (!p) continue
      const prev = agg.get(p) ?? { wins: 0, draws: 0, matches: 0 }
      prev.wins += row.wins
      prev.draws += row.draws
      prev.matches += row.matches
      agg.set(p, prev)
    }
    for (const [p, v] of agg.entries()) {
      const denom = v.matches || 0
      const wr = denom ? (v.wins + 0.5 * v.draws) / denom : 0
      map.set(p, wr)
    }
    return map
  }, [playersSummary])

  return (
    <div className="page">
      <h1 className="page-title">Matchups</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
        {dataMode === 'archetypes'
          ? 'Archetype vs archetype win rates from event feedback. Only pairs with at least the minimum number of matches (set in Settings by admin) are shown.'
          : 'Player vs player win rates from event feedback. Only pairs with at least the minimum number of matches for players (set in Settings by admin) are shown.'}
      </p>

      <div className="table-wrap-outer" style={{ marginBottom: '1.5rem' }}>
        <div className="table-wrap" style={{ overflow: 'visible' }}>
          <FiltersPanel>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label htmlFor="matchups-format">Format</label>
              <select
                id="matchups-format"
                value={formatId}
                onChange={(e) => setFormatId(e.target.value)}
                aria-label="Format"
                style={{ minWidth: 120 }}
              >
                <option value="">All formats</option>
                {[...new Set(events.map((e) => e.format_id).filter(Boolean))].sort().map((f) => (
                  <option key={f} value={f}>{f}</option>
                ))}
              </select>
            </div>
            {dataMode === 'archetypes' && (
            <div className="form-group event-selector-wrap" style={{ marginBottom: 0, width: '100%', maxWidth: 280, minWidth: 0 }} ref={archetypeRef}>
              <label htmlFor="matchups-archetype">Archetype</label>
              <div style={{ position: 'relative' }}>
                <button
                  ref={archetypeButtonRef}
                  id="matchups-archetype"
                  type="button"
                  onClick={() => setArchetypeOpen((o) => !o)}
                  aria-expanded={archetypeOpen}
                  aria-haspopup="listbox"
                  aria-label="Select archetypes"
                  style={{
                    width: '100%',
                    minWidth: 0,
                    padding: '0.5rem 0.75rem',
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    borderRadius: 6,
                    color: 'var(--text)',
                    fontSize: '1rem',
                    textAlign: 'left',
                    cursor: 'pointer',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {selectedArchetypes.length === 0
                    ? 'All archetypes'
                    : selectedArchetypes.length === 1
                      ? selectedArchetypes[0]
                      : `${selectedArchetypes.length} archetypes selected`}
                </button>
                {archetypeOpen && (
                  <div
                    className="events-dropdown"
                    role="listbox"
                    aria-multiselectable
                    aria-label="Archetypes"
                    style={{
                      position: 'absolute',
                      left: 0,
                      width: 280,
                      ...(archetypeFlipAbove
                        ? { bottom: '100%', marginBottom: DROPDOWN_GAP, marginTop: 0 }
                        : { top: '100%', marginTop: DROPDOWN_GAP }),
                      maxHeight: archetypeMaxHeight,
                      overflowY: 'auto',
                      background: 'var(--bg-card)',
                      border: '1px solid var(--border)',
                      borderRadius: 6,
                      zIndex: 100,
                      padding: '0.35rem',
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        gap: '0.75rem',
                        marginBottom: '0.35rem',
                        paddingBottom: '0.35rem',
                        borderBottom: '1px solid var(--border)',
                      }}
                    >
                      <button
                        type="button"
                        onClick={() => setSelectedArchetypes([])}
                        style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: '0.8rem' }}
                      >
                        Clear
                      </button>
                      <button
                        type="button"
                        onClick={() => setSelectedArchetypes([...archetypeOptions])}
                        style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: '0.8rem' }}
                      >
                        Select all
                      </button>
                    </div>
                    {archetypeOptions.map((name) => (
                      <label
                        key={name}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.25rem',
                          padding: '0.2rem 0',
                          cursor: 'pointer',
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={selectedArchetypes.includes(name)}
                          onChange={() => toggleArchetype(name)}
                          style={{ flexShrink: 0 }}
                        />
                        <span style={{ fontSize: '0.9rem', wordBreak: 'break-word', minWidth: 0, flex: 1 }}>{name}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            </div>
            )}
            {dataMode === 'players' && (
            <div className="form-group event-selector-wrap" style={{ marginBottom: 0, width: '100%', maxWidth: 280, minWidth: 0 }} ref={playerRef}>
              <label htmlFor="matchups-player">Player</label>
              <div style={{ position: 'relative' }}>
                <button
                  ref={playerButtonRef}
                  id="matchups-player"
                  type="button"
                  onClick={() => setPlayerOpen((o) => !o)}
                  aria-expanded={playerOpen}
                  aria-haspopup="listbox"
                  aria-label="Select players"
                  style={{
                    width: '100%',
                    minWidth: 0,
                    padding: '0.5rem 0.75rem',
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    borderRadius: 6,
                    color: 'var(--text)',
                    fontSize: '1rem',
                    textAlign: 'left',
                    cursor: 'pointer',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {selectedPlayers.length === 0
                    ? 'All players'
                    : selectedPlayers.length === 1
                      ? selectedPlayers[0]
                      : `${selectedPlayers.length} players selected`}
                </button>
                {playerOpen && (
                  <div
                    className="events-dropdown"
                    role="listbox"
                    aria-multiselectable
                    aria-label="Players"
                    style={{
                      position: 'absolute',
                      left: 0,
                      width: 280,
                      ...(playerFlipAbove
                        ? { bottom: '100%', marginBottom: DROPDOWN_GAP, marginTop: 0 }
                        : { top: '100%', marginTop: DROPDOWN_GAP }),
                      maxHeight: playerMaxHeight,
                      overflowY: 'auto',
                      background: 'var(--bg-card)',
                      border: '1px solid var(--border)',
                      borderRadius: 6,
                      zIndex: 100,
                      padding: '0.35rem',
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        gap: '0.75rem',
                        marginBottom: '0.35rem',
                        paddingBottom: '0.35rem',
                        borderBottom: '1px solid var(--border)',
                      }}
                    >
                      <button
                        type="button"
                        onClick={() => setSelectedPlayers([])}
                        style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: '0.8rem' }}
                      >
                        Clear
                      </button>
                      <button
                        type="button"
                        onClick={() => setSelectedPlayers([...playerOptions])}
                        style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: '0.8rem' }}
                      >
                        Select all
                      </button>
                    </div>
                    {playerOptions.map((name) => (
                      <label
                        key={name}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.25rem',
                          padding: '0.2rem 0',
                          cursor: 'pointer',
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={selectedPlayers.includes(name)}
                          onChange={() => togglePlayer(name)}
                          style={{ flexShrink: 0 }}
                        />
                        <span style={{ fontSize: '0.9rem', wordBreak: 'break-word', minWidth: 0, flex: 1 }}>{name}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            </div>
            )}
            <EventSelector
              events={events}
              selectedIds={eventIds}
              onChange={setEventIds}
              showDatePresets
              maxDate={maxDate}
              lastEventDate={lastEventDate}
            />
          </FiltersPanel>
        </div>
      </div>

      {dataMode === 'archetypes' && summary && (() => {
        const listFiltered = summary.list.filter((row) => (row.archetype || '').toLowerCase() !== (row.opponent_archetype || '').toLowerCase())
        return (
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
            Showing matchups with ≥ {summary.min_matches} match(es). {listFiltered.length} pair(s). Same-archetype vs same-archetype excluded from list and shown as 50% in matrix. Record is <strong>Wins–Losses–Draws</strong> (e.g. 2–1–0).
          </p>
        )
      })()}
      {dataMode === 'players' && playersSummary && (() => {
        const listFiltered = playersSummary.players_list.filter((row) => (row.player || '').toLowerCase() !== (row.opponent_player || '').toLowerCase())
        return (
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
            Showing player pairs with ≥ {playersSummary.min_matches} match(es). {listFiltered.length} pair(s). Same-player vs same-player excluded from list. Record is <strong>Wins–Losses–Draws</strong> (e.g. 2–1–0).
          </p>
        )
      })()}

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: '0.25rem', marginRight: '0.75rem' }}>
          <button
            type="button"
            className={`btn ${dataMode === 'archetypes' ? 'btn-primary' : ''}`}
            onClick={() => setDataMode('archetypes')}
          >
            Archetypes
          </button>
          <button
            type="button"
            className={`btn ${dataMode === 'players' ? 'btn-primary' : ''}`}
            onClick={() => setDataMode('players')}
          >
            Players
          </button>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            type="button"
            className={`btn ${viewMode === 'matrix' ? 'btn-primary' : ''}`}
            onClick={() => setViewMode('matrix')}
          >
            Matrix
          </button>
          <button
            type="button"
            className={`btn ${viewMode === 'list' ? 'btn-primary' : ''}`}
            onClick={() => setViewMode('list')}
          >
            List
          </button>
          <label style={{ fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <input
              type="checkbox"
              checked={sortByWinRate}
              onChange={(e) => setSortByWinRate(e.target.checked)}
            />
            Sort rows by win rate
          </label>
        </div>
      </div>

      {(loading && dataMode === 'archetypes') || (playersLoading && dataMode === 'players') ? (
        <>
          <Skeleton width="100%" height={120} style={{ marginBottom: '0.5rem' }} />
          <Skeleton width="100%" height={120} style={{ marginBottom: '0.5rem' }} />
          <Skeleton width="100%" height={120} />
        </>
      ) : null}
      {dataMode === 'archetypes' && error && <p style={{ color: 'var(--danger, #c00)' }}>{error}</p>}
      {dataMode === 'players' && playersError && <p style={{ color: 'var(--danger, #c00)' }}>{playersError}</p>}

      {dataMode === 'archetypes' && !loading && !error && summary && viewMode === 'list' && (() => {
        const listFiltered = summary.list
          .filter((row) => (row.archetype || '').toLowerCase() !== (row.opponent_archetype || '').toLowerCase())
          .slice()
          .sort((a, b) => {
            if (!sortByWinRate) return 0
            if (b.win_rate !== a.win_rate) return b.win_rate - a.win_rate
            return b.matches - a.matches
          })
        return (
          <div className="table-wrap-outer">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Your archetype</th>
                    <th scope="col">Opponent archetype</th>
                    <th scope="col" title="Wins – Losses – Draws">Record (W–L–D)</th>
                    <th scope="col">Win rate</th>
                    <th scope="col">Matches</th>
                  </tr>
                </thead>
                <tbody>
                  {listFiltered.map((row, i) => (
                    <tr key={i}>
                      <td>{row.archetype}</td>
                      <td>{row.opponent_archetype}</td>
                      <td title="Wins – Losses – Draws">{row.wins}–{row.losses}–{row.draws}</td>
                      <td>{(row.win_rate * 100).toFixed(1)}%</td>
                      <td>{row.matches}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      })()}

      {dataMode === 'archetypes' && !loading && !error && summary && viewMode === 'matrix' && (() => {
        const singleRowIndex =
          selectedArchetypes.length === 1
            ? summary.archetypes.findIndex((a) => (a || '').toLowerCase() === (selectedArchetypes[0] || '').toLowerCase())
            : -1
        let rowIndices = singleRowIndex >= 0 ? [singleRowIndex] : summary.archetypes.map((_, i) => i)
        let columnIndices = singleRowIndex >= 0
          ? summary.archetypes.map((_, j) => j).filter((j) => j !== singleRowIndex)
          : summary.archetypes.map((_, j) => j)

        if (sortByWinRate) {
          // When a single archetype is selected, sort columns by that row's win rate.
          if (singleRowIndex >= 0) {
            columnIndices = [...columnIndices].sort((i, j) => {
              const wi = summary.matrix[singleRowIndex]?.[i] ?? 0
              const wj = summary.matrix[singleRowIndex]?.[j] ?? 0
              return (wj ?? 0) - (wi ?? 0)
            })
          } else {
            const cmp = (i: number, j: number) => {
              const ai = summary.archetypes[i]
              const aj = summary.archetypes[j]
              const wi = archetypeOverallWinRate.get(ai) ?? 0
              const wj = archetypeOverallWinRate.get(aj) ?? 0
              if (wj !== wi) return wj - wi
              return ai.localeCompare(aj)
            }
            rowIndices = [...rowIndices].sort(cmp)
            columnIndices = [...columnIndices].sort(cmp)
          }
        }
        return (
          <div className="card" style={{ overflow: 'auto' }}>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
              Rows = your archetype, columns = opponent. Cell = your win rate vs that archetype. Heatmap: green = 100%, red = 0%.
            </p>
            <div style={{ minWidth: 400 }}>
              <table style={{ borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                <thead>
                  <tr>
                    <th style={{ padding: '0.35rem', textAlign: 'left', position: 'sticky', left: 0, background: 'var(--bg-card)' }} />
                    {columnIndices.map((j) => {
                      const a = summary.archetypes[j]
                      return (
                        <th key={a} style={{ padding: '0.35rem', maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis' }} title={a}>
                          {a.length > 12 ? a.slice(0, 11) + '…' : a}
                        </th>
                      )
                    })}
                  </tr>
                </thead>
                <tbody>
                  {rowIndices.map((i) => {
                    const a = summary.archetypes[i]
                    return (
                      <tr key={a}>
                        <td style={{ padding: '0.35rem', position: 'sticky', left: 0, background: 'var(--bg-card)', whiteSpace: 'nowrap', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis' }} title={a}>
                          {a.length > 14 ? a.slice(0, 13) + '…' : a}
                        </td>
                        {columnIndices.map((j) => {
                          const cell = summary.matrix[i]![j]
                          if (i === j) return <td key={j} style={{ padding: '0.35rem', backgroundColor: 'rgba(128,128,128,0.2)' }} title="Same archetype"> </td>
                          if (cell == null) return <td key={j} style={{ padding: '0.35rem', color: 'var(--text-muted)' }}>—</td>
                          const pct = cell * 100
                          const opponent = summary.archetypes[j]
                          const key = `${a}|||${opponent}`
                          const matchupRow = matchupsByPair.get(key)
                          return (
                            <td
                              key={j}
                              style={{ padding: '0.35rem', backgroundColor: heatmapColor(pct), cursor: matchupRow ? 'help' : 'default' }}
                              onMouseEnter={(e) => {
                                if (!matchupRow) return
                                setHoveredCell({ archetype: a, opponent, rect: e.currentTarget.getBoundingClientRect() })
                              }}
                              onMouseMove={(e) => {
                                if (!matchupRow) return
                                setHoveredCell({ archetype: a, opponent, rect: e.currentTarget.getBoundingClientRect() })
                              }}
                              onMouseLeave={() => setHoveredCell(null)}
                              onFocus={(e) => {
                                if (!matchupRow) return
                                setHoveredCell({ archetype: a, opponent, rect: e.currentTarget.getBoundingClientRect() })
                              }}
                              onBlur={() => setHoveredCell(null)}
                              tabIndex={matchupRow ? 0 : -1}
                              aria-label={matchupRow ? `${a} vs ${opponent}` : undefined}
                            >
                              {pct.toFixed(0)}%
                            </td>
                          )
                        })}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {hoveredCell && (() => {
              const row = matchupsByPair.get(`${hoveredCell.archetype}|||${hoveredCell.opponent}`)
              if (!row) return null
              const drawPct = row.matches > 0 ? (row.draws / row.matches) * 100 : 0
              const pos = getTooltipPosition(hoveredCell.rect)
              return (
                <div
                  role="tooltip"
                  style={{
                    position: 'fixed',
                    left: pos.left,
                    top: pos.top,
                    transform: pos.transform,
                    zIndex: 1000,
                    pointerEvents: 'none',
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border)',
                    borderRadius: 8,
                    padding: '0.5rem 0.6rem',
                    color: 'var(--text)',
                    boxShadow: '0 10px 26px rgba(0,0,0,0.25)',
                    minWidth: 220,
                    maxWidth: 320,
                    fontSize: '0.85rem',
                    lineHeight: 1.25,
                  }}
                >
                  <div style={{ fontWeight: 700, marginBottom: '0.35rem' }}>
                    {row.archetype} vs {row.opponent_archetype}
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', columnGap: '0.75rem', rowGap: '0.2rem' }}>
                    <div style={{ color: 'var(--text-muted)' }}>Win %</div>
                    <div style={{ textAlign: 'right' }}>{(row.win_rate * 100).toFixed(1)}%</div>
                    <div style={{ color: 'var(--text-muted)' }}>Draw %</div>
                    <div style={{ textAlign: 'right' }}>{drawPct.toFixed(1)}%</div>
                    <div style={{ color: 'var(--text-muted)' }}>Record</div>
                    <div style={{ textAlign: 'right' }}>{row.wins}–{row.losses}–{row.draws}</div>
                    <div style={{ color: 'var(--text-muted)' }}>Matches</div>
                    <div style={{ textAlign: 'right' }}>{row.matches}</div>
                  </div>
                </div>
              )
            })()}
          </div>
        )
      })()}

      {dataMode === 'players' && !playersLoading && !playersError && playersSummary && viewMode === 'list' && (() => {
        const listFiltered = playersSummary.players_list
          .filter((row) => (row.player || '').toLowerCase() !== (row.opponent_player || '').toLowerCase())
          .slice()
          .sort((a, b) => {
            if (!sortByWinRate) return 0
            if (b.win_rate !== a.win_rate) return b.win_rate - a.win_rate
            return b.matches - a.matches
          })
        return (
          <div className="table-wrap-outer">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Player A</th>
                    <th scope="col">Player B</th>
                    <th scope="col" title="Wins – Losses – Draws">Record (W–L–D)</th>
                    <th scope="col">Win rate</th>
                    <th scope="col">Matches</th>
                  </tr>
                </thead>
                <tbody>
                  {listFiltered.map((row, i) => (
                    <tr key={i}>
                      <td>{row.player}</td>
                      <td>{row.opponent_player}</td>
                      <td title="Wins – Losses – Draws">{row.wins}–{row.losses}–{row.draws}</td>
                      <td>{(row.win_rate * 100).toFixed(1)}%</td>
                      <td>{row.matches}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      })()}

      {dataMode === 'players' && !playersLoading && !playersError && playersSummary && viewMode === 'matrix' && (() => {
        const singleRowIndex =
          selectedPlayers.length === 1
            ? playersSummary.players.findIndex((p) => (p || '').toLowerCase() === (selectedPlayers[0] || '').toLowerCase())
            : -1
        let rowIndices = singleRowIndex >= 0 ? [singleRowIndex] : playersSummary.players.map((_, i) => i)
        let columnIndices = singleRowIndex >= 0
          ? playersSummary.players.map((_, j) => j).filter((j) => j !== singleRowIndex)
          : playersSummary.players.map((_, j) => j)

        if (sortByWinRate) {
          if (singleRowIndex >= 0) {
            columnIndices = [...columnIndices].sort((i, j) => {
              const wi = playersSummary.players_matrix[singleRowIndex]?.[i] ?? 0
              const wj = playersSummary.players_matrix[singleRowIndex]?.[j] ?? 0
              return (wj ?? 0) - (wi ?? 0)
            })
          } else {
            const cmp = (i: number, j: number) => {
              const pi = playersSummary.players[i]
              const pj = playersSummary.players[j]
              const wi = playersOverallWinRate.get(pi) ?? 0
              const wj = playersOverallWinRate.get(pj) ?? 0
              if (wj !== wi) return wj - wi
              return pi.localeCompare(pj)
            }
            rowIndices = [...rowIndices].sort(cmp)
            columnIndices = [...columnIndices].sort(cmp)
          }
        }
        return (
        <div className="card" style={{ overflow: 'auto' }}>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
            Rows = player, columns = opponent. Cell = row player&apos;s win rate vs column player. Heatmap: green = 100%, red = 0%.
          </p>
          {playersSummary.players.length === 0 ? (
            <p style={{ color: 'var(--text-muted)' }}>No player matchup data for the selected filters.</p>
          ) : (
            <div style={{ minWidth: 400 }}>
              <table style={{ borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                <thead>
                  <tr>
                    <th style={{ padding: '0.35rem', textAlign: 'left', position: 'sticky', left: 0, background: 'var(--bg-card)' }} />
                    {columnIndices.map((j) => {
                      const p = playersSummary.players[j]
                      return (
                        <th key={p} style={{ padding: '0.35rem', maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis' }} title={p}>
                          {p.length > 12 ? p.slice(0, 11) + '…' : p}
                        </th>
                      )
                    })}
                  </tr>
                </thead>
                <tbody>
                  {rowIndices.map((i) => {
                    const pa = playersSummary.players[i]
                    return (
                      <tr key={pa}>
                        <td style={{ padding: '0.35rem', position: 'sticky', left: 0, background: 'var(--bg-card)', whiteSpace: 'nowrap', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis' }} title={pa}>
                          {pa.length > 14 ? pa.slice(0, 13) + '…' : pa}
                        </td>
                        {columnIndices.map((j) => {
                          const pb = playersSummary.players[j]
                          if (i === j) return <td key={pb} style={{ padding: '0.35rem', backgroundColor: 'rgba(128,128,128,0.2)' }} title="Same player"> </td>
                          const cell = playersSummary.players_matrix[i]?.[j]
                          if (cell == null) return <td key={pb} style={{ padding: '0.35rem', color: 'var(--text-muted)' }}>—</td>
                          const pct = cell * 100
                          const matchupRow = playersByPair.get(`${pa}|||${pb}`)
                          return (
                            <td
                              key={pb}
                              style={{ padding: '0.35rem', backgroundColor: heatmapColor(pct), cursor: matchupRow ? 'help' : 'default' }}
                              onMouseEnter={(e) => {
                                if (!matchupRow) return
                                setHoveredPlayerCell({ player: pa, opponent: pb, rect: e.currentTarget.getBoundingClientRect() })
                              }}
                              onMouseMove={(e) => {
                                if (!matchupRow) return
                                setHoveredPlayerCell({ player: pa, opponent: pb, rect: e.currentTarget.getBoundingClientRect() })
                              }}
                              onMouseLeave={() => setHoveredPlayerCell(null)}
                              onFocus={(e) => {
                                if (!matchupRow) return
                                setHoveredPlayerCell({ player: pa, opponent: pb, rect: e.currentTarget.getBoundingClientRect() })
                              }}
                              onBlur={() => setHoveredPlayerCell(null)}
                              tabIndex={matchupRow ? 0 : -1}
                              aria-label={matchupRow ? `${pa} vs ${pb}` : undefined}
                            >
                              {pct.toFixed(0)}%
                            </td>
                          )
                        })}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              {hoveredPlayerCell && (() => {
                const row = playersByPair.get(`${hoveredPlayerCell.player}|||${hoveredPlayerCell.opponent}`)
                if (!row) return null
                const drawPct = row.matches > 0 ? (row.draws / row.matches) * 100 : 0
                const pos = getTooltipPosition(hoveredPlayerCell.rect)
                return (
                  <div
                    role="tooltip"
                    style={{
                      position: 'fixed',
                      left: pos.left,
                      top: pos.top,
                      transform: pos.transform,
                      zIndex: 1000,
                      pointerEvents: 'none',
                      background: 'var(--bg-card)',
                      border: '1px solid var(--border)',
                      borderRadius: 8,
                      padding: '0.5rem 0.6rem',
                      color: 'var(--text)',
                      boxShadow: '0 10px 26px rgba(0,0,0,0.25)',
                      minWidth: 220,
                      maxWidth: 320,
                      fontSize: '0.85rem',
                      lineHeight: 1.25,
                    }}
                  >
                    <div style={{ fontWeight: 700, marginBottom: '0.35rem' }}>
                      {row.player} vs {row.opponent_player}
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', columnGap: '0.75rem', rowGap: '0.2rem' }}>
                      <div style={{ color: 'var(--text-muted)' }}>Win %</div>
                      <div style={{ textAlign: 'right' }}>{(row.win_rate * 100).toFixed(1)}%</div>
                      <div style={{ color: 'var(--text-muted)' }}>Draw %</div>
                      <div style={{ textAlign: 'right' }}>{drawPct.toFixed(1)}%</div>
                      <div style={{ color: 'var(--text-muted)' }}>Record</div>
                      <div style={{ textAlign: 'right' }}>{row.wins}–{row.losses}–{row.draws}</div>
                      <div style={{ color: 'var(--text-muted)' }}>Matches</div>
                      <div style={{ textAlign: 'right' }}>{row.matches}</div>
                    </div>
                  </div>
                )
              })()}
            </div>
          )}
        </div>
        )
      })()}

      {dataMode === 'archetypes' && !loading && !error && summary && summary.list.filter((row) => (row.archetype || '').toLowerCase() !== (row.opponent_archetype || '').toLowerCase()).length === 0 && (
        <p style={{ color: 'var(--text-muted)' }}>No matchup data for the selected filters.</p>
      )}
      {dataMode === 'players' && !playersLoading && !playersError && playersSummary && playersSummary.players_list.length === 0 && (
        <p style={{ color: 'var(--text-muted)' }}>No player matchup data for the selected filters.</p>
      )}
    </div>
  )
}
