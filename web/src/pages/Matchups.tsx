import { useEffect, useRef, useState } from 'react'
import { getMatchupsSummary } from '../api'
import EventSelector from '../components/EventSelector'
import FiltersPanel from '../components/FiltersPanel'
import { useEventMetadata } from '../hooks/useEventMetadata'
import Skeleton from '../components/Skeleton'
import toast from 'react-hot-toast'
import { reportError } from '../utils'

const DROPDOWN_MAX_HEIGHT = 240
const DROPDOWN_GAP = 4

type ViewMode = 'list' | 'matrix'

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
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [formatId, setFormatId] = useState('')
  const [eventIds, setEventIds] = useState<(number | string)[]>([])
  const [selectedArchetypes, setSelectedArchetypes] = useState<string[]>([])
  const [archetypeOptions, setArchetypeOptions] = useState<string[]>([])
  const [archetypeOpen, setArchetypeOpen] = useState(false)
  const [viewMode, setViewMode] = useState<ViewMode>('matrix')
  const archetypeRef = useRef<HTMLDivElement>(null)
  const archetypeButtonRef = useRef<HTMLButtonElement>(null)
  const [archetypeFlipAbove, setArchetypeFlipAbove] = useState(false)
  const [archetypeMaxHeight, setArchetypeMaxHeight] = useState(DROPDOWN_MAX_HEIGHT)

  useEffect(() => {
    if (eventMetadataError) toast.error(reportError(new Error(eventMetadataError)))
  }, [eventMetadataError])

  useEffect(() => {
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
  }, [formatId, eventIds, selectedArchetypes])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (archetypeRef.current && !archetypeRef.current.contains(e.target as Node)) setArchetypeOpen(false)
    }
    if (archetypeOpen) document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [archetypeOpen])

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

  const toggleArchetype = (name: string) => {
    setSelectedArchetypes((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return [...next]
    })
  }

  return (
    <div className="page">
      <h1 className="page-title">Matchups</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
        Archetype vs archetype win rates from event feedback. Only pairs with at least the minimum number of matches (set in Settings by admin) are shown.
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

      {summary && (() => {
        const listFiltered = summary.list.filter((row) => row.archetype !== row.opponent_archetype)
        return (
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
            Showing matchups with ≥ {summary.min_matches} match(es). {listFiltered.length} pair(s). Same-archetype vs same-archetype excluded from list and shown as 50% in matrix. Record is <strong>Wins–Losses–Draws</strong> (e.g. 2–1–0).
          </p>
        )
      })()}

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
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
      </div>

      {loading && (
        <>
          <Skeleton width="100%" height={120} style={{ marginBottom: '0.5rem' }} />
          <Skeleton width="100%" height={120} style={{ marginBottom: '0.5rem' }} />
          <Skeleton width="100%" height={120} />
        </>
      )}
      {error && <p style={{ color: 'var(--danger, #c00)' }}>{error}</p>}

      {!loading && !error && summary && viewMode === 'list' && (() => {
        const listFiltered = summary.list.filter((row) => row.archetype !== row.opponent_archetype)
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

      {!loading && !error && summary && viewMode === 'matrix' && (() => {
        const singleRowIndex = selectedArchetypes.length === 1 ? summary.archetypes.indexOf(selectedArchetypes[0]) : -1
        const rowIndices = singleRowIndex >= 0 ? [singleRowIndex] : summary.archetypes.map((_, i) => i)
        const columnIndices = singleRowIndex >= 0
          ? summary.archetypes.map((_, j) => j).filter((j) => j !== singleRowIndex)
          : summary.archetypes.map((_, j) => j)
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
                          return (
                            <td
                              key={j}
                              style={{ padding: '0.35rem', backgroundColor: heatmapColor(pct) }}
                              title={`${summary!.archetypes[i]} win rate against ${summary!.archetypes[j]}: ${pct.toFixed(1)}%`}
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
          </div>
        )
      })()}

      {!loading && !error && summary && summary.list.filter((row) => row.archetype !== row.opponent_archetype).length === 0 && (
        <p style={{ color: 'var(--text-muted)' }}>No matchup data for the selected filters.</p>
      )}
    </div>
  )
}
