import { useEffect, useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { getMetagame, getDateRange, getEvents, getFormatInfo } from '../api'
import type { MetagameReport, Event } from '../types'
import EventSelector from '../components/EventSelector'
import Skeleton from '../components/Skeleton'
import ManaSymbols from '../components/ManaSymbols'
import { reportError } from '../utils'

const COLOR_OPTIONS: { value: string; manaCost: string; title: string }[] = [
  { value: 'W', manaCost: '{W}', title: 'White' },
  { value: 'U', manaCost: '{U}', title: 'Blue' },
  { value: 'B', manaCost: '{B}', title: 'Black' },
  { value: 'R', manaCost: '{R}', title: 'Red' },
  { value: 'G', manaCost: '{G}', title: 'Green' },
  { value: 'C', manaCost: '{C}', title: 'Colorless' },
]

export default function Archetypes() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [metagame, setMetagame] = useState<MetagameReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [eventIds, setEventIds] = useState<(number | string)[]>(() => {
    const param = searchParams.get('event_ids') ?? searchParams.get('event_id')
    if (!param) return []
    return param.split(',').map((s) => s.trim()).filter(Boolean)
  })
  const [maxDate, setMaxDate] = useState<string | null>(null)
  const [lastEventDate, setLastEventDate] = useState<string | null>(null)
  const [events, setEvents] = useState<Event[]>([])
  const [formatName, setFormatName] = useState<string | null>(null)
  type SortKey = 'archetype' | 'count' | 'pct' | 'countTop8' | 'pctTop8' | 'conversion'
  const [sortBy, setSortBy] = useState<SortKey>('pct')
  const [sortDesc, setSortDesc] = useState(true)
  const [filterColors, setFilterColors] = useState<string[]>([])

  useEffect(() => {
    const param = searchParams.get('event_ids') ?? searchParams.get('event_id')
    if (!param) setEventIds([])
    else setEventIds(param.split(',').map((s) => s.trim()).filter(Boolean))
  }, [searchParams])

  useEffect(() => {
    getDateRange().then((r) => {
      setMaxDate(r.max_date)
      setLastEventDate(r.last_event_date)
    })
    getEvents().then((r) => setEvents(r.events))
    getFormatInfo().then((r) => setFormatName(r.format_name))
  }, [])

  useEffect(() => {
    setLoading(true)
    const eventIdsParam = eventIds.length ? eventIds.map(String).join(',') : undefined
    getMetagame(false, false, undefined, undefined, undefined, eventIdsParam, false, true)
      .then(setMetagame)
      .catch((e) => {
        setError(e.message)
        toast.error(reportError(e))
      })
      .finally(() => setLoading(false))
  }, [eventIds])

  const setEventFilter = (ids: (number | string)[]) => {
    setEventIds(ids)
    if (ids.length === 0) {
      setSearchParams({})
    } else {
      setSearchParams({ event_ids: ids.map(String).join(',') })
    }
  }

  const archetypes = metagame?.archetype_distribution ?? []
  const archetypesTop8 = metagame?.archetype_distribution_top8 ?? []
  const byName: Record<string, { archetype: string; count: number; pct: number; countTop8: number; pctTop8: number; conversion: number; colors?: string[] }> = {}
  for (const r of archetypes) {
    byName[r.archetype] = { ...r, countTop8: 0, pctTop8: 0, conversion: 0 }
  }
  for (const r of archetypesTop8) {
    if (!byName[r.archetype]) {
      byName[r.archetype] = { archetype: r.archetype, count: 0, pct: 0, countTop8: r.count, pctTop8: r.pct, conversion: 0, colors: r.colors }
    } else {
      byName[r.archetype].countTop8 = r.count
      byName[r.archetype].pctTop8 = r.pct
    }
  }
  for (const row of Object.values(byName)) {
    row.conversion = row.count > 0 ? Math.round((row.countTop8 / row.count) * 1000) / 10 : 0
  }
  const handleSort = (key: SortKey) => {
    if (sortBy === key) {
      setSortDesc((d) => !d)
    } else {
      setSortBy(key)
      setSortDesc(key === 'archetype' ? false : true)
    }
  }
  const rows = Object.values(byName)
  const filteredRows = rows.filter((row) => {
    if (filterColors.length === 0) return true
    const colors = row.colors ?? archetypes.find((a) => a.archetype === row.archetype)?.colors ?? []
    if (!colors.length) return false
    const set = new Set(colors)
    return filterColors.every((c) => set.has(c))
  })

  const sortedRows = filteredRows.sort((a, b) => {
    let cmp = 0
    switch (sortBy) {
      case 'archetype':
        cmp = (a.archetype || '').localeCompare(b.archetype || '')
        break
      case 'count':
        cmp = a.count - b.count
        break
      case 'pct':
        cmp = a.pct - b.pct
        break
      case 'countTop8':
        cmp = a.countTop8 - b.countTop8
        break
      case 'pctTop8':
        cmp = a.pctTop8 - b.pctTop8
        break
      case 'conversion':
        cmp = a.conversion - b.conversion
        break
    }
    return sortDesc ? -cmp : cmp
  })

  if (loading && !metagame) {
    return (
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '0.75rem' }}>
          <Skeleton width={220} height={32} />
          <Skeleton width={280} height={40} />
        </div>
        <div className="chart-container">
          <Skeleton width="100%" height={400} />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div>
        <h1 className="page-title">Archetypes</h1>
        <div className="chart-container" style={{ textAlign: 'center', padding: '2rem' }}>
          <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>{error}</p>
          <button
            type="button"
            className="btn"
            onClick={() => {
              setError(null)
              setLoading(true)
              const eventIdsParam = eventIds.length ? eventIds.map(String).join(',') : undefined
              getMetagame(false, false, undefined, undefined, undefined, eventIdsParam, false, true)
                .then(setMetagame)
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

  return (
    <div style={{ opacity: loading ? 0.6 : 1, transition: 'opacity 0.2s' }}>
      <div className="toolbar toolbar--stack-on-mobile" style={{ justifyContent: 'space-between', marginBottom: '1.5rem', gap: '0.75rem' }}>
        <h1 className="page-title" style={{ margin: 0 }}>
          Archetypes{formatName && <span style={{ fontSize: '0.7em', color: 'var(--text-muted)', marginLeft: '0.5rem' }}>— {formatName}</span>}
        </h1>
        <div
          className="archetypes-events-filter toolbar"
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

      {sortedRows.length === 0 ? (
        <div className="chart-container" style={{ textAlign: 'center', padding: '2rem' }}>
          <p style={{ color: 'var(--text-muted)' }}>No archetype data. Load or scrape data to see archetypes.</p>
        </div>
      ) : (
        <div className="chart-container">
          <p style={{ margin: '0 0 1rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            Click column headers to sort. Conversion = % of that archetype&apos;s decks that made top 8. Click an archetype for average deck stats and most played cards.
          </p>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Filter by color:</span>
            {COLOR_OPTIONS.map((opt) => {
              const active = filterColors.includes(opt.value)
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => {
                    setFilterColors((prev) => {
                      const set = new Set(prev)
                      if (set.has(opt.value)) set.delete(opt.value)
                      else set.add(opt.value)
                      return Array.from(set)
                    })
                  }}
                  style={{
                    borderRadius: 999,
                    border: active ? '1px solid var(--accent)' : '1px solid var(--border)',
                    padding: '0.1rem 0.4rem',
                    background: active ? 'var(--accent-soft, var(--accent))' : 'transparent',
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 4,
                    opacity: active ? 1 : 0.9,
                  }}
                  aria-pressed={active}
                  title={opt.title}
                >
                  <ManaSymbols manaCost={opt.manaCost} size={16} />
                </button>
              )
            })}
            {filterColors.length > 0 && (
              <button
                type="button"
                className="btn"
                style={{ padding: '0.15rem 0.5rem', fontSize: '0.75rem' }}
                onClick={() => setFilterColors([])}
              >
                Clear colors
              </button>
            )}
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table className="table">
              <thead>
                <tr>
                  <th
                    style={{ cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('archetype')}
                    title="Sort by archetype"
                    aria-sort={sortBy === 'archetype' ? (sortDesc ? 'descending' : 'ascending') : undefined}
                  >
                    Archetype {sortBy === 'archetype' && (sortDesc ? '↓' : '↑')}
                  </th>
                  <th
                    style={{ textAlign: 'right', cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('count')}
                    title="Sort by decks"
                    aria-sort={sortBy === 'count' ? (sortDesc ? 'descending' : 'ascending') : undefined}
                  >
                    Decks {sortBy === 'count' && (sortDesc ? '↓' : '↑')}
                  </th>
                  <th
                    style={{ textAlign: 'right', cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('pct')}
                    title="Sort by % of metagame"
                    aria-sort={sortBy === 'pct' ? (sortDesc ? 'descending' : 'ascending') : undefined}
                  >
                    % of metagame {sortBy === 'pct' && (sortDesc ? '↓' : '↑')}
                  </th>
                  <th
                    style={{ textAlign: 'right', cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('countTop8')}
                    title="Sort by decks (top 8)"
                    aria-sort={sortBy === 'countTop8' ? (sortDesc ? 'descending' : 'ascending') : undefined}
                  >
                    Decks (Top 8) {sortBy === 'countTop8' && (sortDesc ? '↓' : '↑')}
                  </th>
                  <th
                    style={{ textAlign: 'right', cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('pctTop8')}
                    title="Sort by % of top 8"
                    aria-sort={sortBy === 'pctTop8' ? (sortDesc ? 'descending' : 'ascending') : undefined}
                  >
                    % of top 8 {sortBy === 'pctTop8' && (sortDesc ? '↓' : '↑')}
                  </th>
                  <th
                    style={{ textAlign: 'right', cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('conversion')}
                    title="Sort by conversion rate (share of archetype decks that made top 8)"
                    aria-sort={sortBy === 'conversion' ? (sortDesc ? 'descending' : 'ascending') : undefined}
                  >
                    Conversion {sortBy === 'conversion' && (sortDesc ? '↓' : '↑')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {sortedRows.map((row) => {
                  const colors = row.colors ?? archetypes.find((a) => a.archetype === row.archetype)?.colors
                  const manaCost = colors && colors.length ? `{${colors.join('}{')}}` : ''
                  return (
                    <tr key={row.archetype}>
                      <td>
                        <Link
                          to={`/archetypes/${encodeURIComponent(row.archetype)}${eventIds.length ? `?event_ids=${encodeURIComponent(eventIds.map(String).join(','))}` : ''}`}
                          style={{ color: 'var(--accent)', fontWeight: 500 }}
                        >
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            {row.archetype}
                            {manaCost && <ManaSymbols manaCost={manaCost} size={18} />}
                          </span>
                        </Link>
                      </td>
                      <td style={{ textAlign: 'right' }}>{row.count}</td>
                      <td style={{ textAlign: 'right' }}>{row.pct}%</td>
                      <td style={{ textAlign: 'right' }}>{row.countTop8}</td>
                      <td style={{ textAlign: 'right' }}>{row.pctTop8 > 0 ? `${row.pctTop8}%` : '—'}</td>
                      <td style={{ textAlign: 'right' }} title={`${row.countTop8} / ${row.count} decks`}>
                        {row.count > 0 ? `${row.conversion}%` : '—'}
                      </td>
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
