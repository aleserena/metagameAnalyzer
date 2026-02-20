import { useEffect, useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { getMetagame, getDateRange, getEvents, getFormatInfo } from '../api'
import type { MetagameReport, Event } from '../types'
import EventSelector from '../components/EventSelector'
import Skeleton from '../components/Skeleton'
import { reportError } from '../utils'

export default function Archetypes() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [metagame, setMetagame] = useState<MetagameReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [eventIds, setEventIds] = useState<number[]>(() => {
    const param = searchParams.get('event_ids') ?? searchParams.get('event_id')
    if (!param) return []
    return param.split(',').map((s) => parseInt(s.trim(), 10)).filter((n) => !isNaN(n))
  })
  const [maxDate, setMaxDate] = useState<string | null>(null)
  const [lastEventDate, setLastEventDate] = useState<string | null>(null)
  const [events, setEvents] = useState<Event[]>([])
  const [formatName, setFormatName] = useState<string | null>(null)

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
    getEvents().then((r) => setEvents(r.events))
    getFormatInfo().then((r) => setFormatName(r.format_name))
  }, [])

  useEffect(() => {
    setLoading(true)
    const eventIdsParam = eventIds.length ? eventIds.join(',') : undefined
    getMetagame(false, false, undefined, undefined, undefined, eventIdsParam)
      .then(setMetagame)
      .catch((e) => {
        setError(e.message)
        toast.error(reportError(e))
      })
      .finally(() => setLoading(false))
  }, [eventIds])

  const setEventFilter = (ids: number[]) => {
    setEventIds(ids)
    if (ids.length === 0) {
      setSearchParams({})
    } else {
      setSearchParams({ event_ids: ids.join(',') })
    }
  }

  const archetypes = metagame?.archetype_distribution ?? []
  const sortedByPct = [...archetypes].sort((a, b) => b.pct - a.pct)

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
              const eventIdsParam = eventIds.length ? eventIds.join(',') : undefined
              getMetagame(false, false, undefined, undefined, undefined, eventIdsParam)
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '0.75rem' }}>
        <h1 className="page-title" style={{ margin: 0 }}>
          Archetypes{formatName && <span style={{ fontSize: '0.7em', color: 'var(--text-muted)', marginLeft: '0.5rem' }}>— {formatName}</span>}
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

      {sortedByPct.length === 0 ? (
        <div className="chart-container" style={{ textAlign: 'center', padding: '2rem' }}>
          <p style={{ color: 'var(--text-muted)' }}>No archetype data. Load or scrape data to see archetypes.</p>
        </div>
      ) : (
        <div className="chart-container">
          <p style={{ margin: '0 0 1rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            Sorted by share of metagame. Click an archetype for average deck stats and most played cards.
          </p>
          <div style={{ overflowX: 'auto' }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Archetype</th>
                  <th style={{ textAlign: 'right' }}>Decks</th>
                  <th style={{ textAlign: 'right' }}>% of metagame</th>
                </tr>
              </thead>
              <tbody>
                {sortedByPct.map((row) => (
                  <tr key={row.archetype}>
                    <td>
                      <Link
                        to={`/archetypes/${encodeURIComponent(row.archetype)}${eventIds.length ? `?event_ids=${eventIds.join(',')}` : ''}`}
                        style={{ color: 'var(--accent)', fontWeight: 500 }}
                      >
                        {row.archetype}
                      </Link>
                    </td>
                    <td style={{ textAlign: 'right' }}>{row.count}</td>
                    <td style={{ textAlign: 'right' }}>{row.pct}%</td>
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
