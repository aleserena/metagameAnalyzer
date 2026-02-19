import { useEffect, useRef, useState } from 'react'
import type { Event } from '../types'
import { dateMinusDays, dateInRange, firstDayOfYear } from '../utils'

export interface EventSelectorProps {
  events: Event[]
  selectedIds: number[]
  onChange: (ids: number[]) => void
  showDatePresets?: boolean
  maxDate?: string | null
  lastEventDate?: string | null
}

const DROPDOWN_MAX_HEIGHT = 240
const DROPDOWN_GAP = 4

export default function EventSelector({
  events,
  selectedIds,
  onChange,
  showDatePresets = false,
  maxDate = null,
  lastEventDate = null,
}: EventSelectorProps) {
  const [open, setOpen] = useState(false)
  const [flipAbove, setFlipAbove] = useState(false)
  const [maxHeight, setMaxHeight] = useState(DROPDOWN_MAX_HEIGHT)
  const ref = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    if (open) document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [open])

  useEffect(() => {
    if (!open || !buttonRef.current) return
    const rect = buttonRef.current.getBoundingClientRect()
    const spaceBelow = window.innerHeight - rect.bottom - DROPDOWN_GAP
    const spaceAbove = rect.top - DROPDOWN_GAP
    const shouldFlip = spaceBelow < DROPDOWN_MAX_HEIGHT && spaceAbove > spaceBelow
    setFlipAbove(shouldFlip)
    const available = shouldFlip ? spaceAbove : spaceBelow
    setMaxHeight(Math.min(DROPDOWN_MAX_HEIGHT, Math.max(100, available)))
  }, [open])

  const setPreset = (preset: 'all' | '2weeks' | 'month' | '2months' | '6months' | 'thisYear' | 'lastEvent') => {
    if (preset === 'all' || !maxDate) {
      onChange([])
      return
    }
    if (preset === 'lastEvent' && lastEventDate) {
      const ids = events.filter((e) => e.date === lastEventDate).map((e) => e.event_id)
      onChange(ids)
      return
    }
    const to = maxDate
    const from =
      preset === '2weeks'
        ? dateMinusDays(maxDate, 14)
        : preset === 'month'
          ? dateMinusDays(maxDate, 30)
          : preset === '2months'
            ? dateMinusDays(maxDate, 60)
            : preset === '6months'
              ? dateMinusDays(maxDate, 183)
              : firstDayOfYear(maxDate)
    const ids = events.filter((e) => dateInRange(e.date, from, to)).map((e) => e.event_id)
    onChange(ids)
  }

  const toggleEvent = (id: number) => {
    const next = new Set(selectedIds)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    onChange([...next])
  }

  return (
    <div className="form-group" style={{ marginBottom: 0, width: 280 }} ref={ref}>
      <label>Events</label>
      {showDatePresets && (
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Date range:</span>
          <button
            type="button"
            className="btn"
            style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }}
            onClick={() => setPreset('all')}
          >
            All time
          </button>
          <button
            type="button"
            className="btn"
            style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }}
            onClick={() => setPreset('thisYear')}
          >
            This year
          </button>
          <button
            type="button"
            className="btn"
            style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }}
            onClick={() => setPreset('6months')}
          >
            6 months
          </button>
          <button
            type="button"
            className="btn"
            style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }}
            onClick={() => setPreset('2months')}
          >
            2 months
          </button>
          <button
            type="button"
            className="btn"
            style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }}
            onClick={() => setPreset('month')}
          >
            Last month
          </button>
          <button
            type="button"
            className="btn"
            style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }}
            onClick={() => setPreset('2weeks')}
          >
            Last 2 weeks
          </button>
          <button
            type="button"
            className="btn"
            style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }}
            onClick={() => setPreset('lastEvent')}
          >
            Last event
          </button>
        </div>
      )}
      <div style={{ position: 'relative' }}>
        <button
          ref={buttonRef}
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-haspopup="listbox"
          aria-label="Select events"
          style={{
            width: '100%',
            minWidth: 280,
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
          {selectedIds.length === 0
            ? 'All events'
            : selectedIds.length === 1
              ? events.find((e) => e.event_id === selectedIds[0])?.event_name ?? '1 event'
              : `${selectedIds.length} events selected`}
        </button>
        {open && (
          <div
            className="events-dropdown"
            role="listbox"
            aria-multiselectable
            aria-label="Events"
            style={{
              position: 'absolute',
              left: 0,
              width: 280,
              ...(flipAbove
                ? { bottom: '100%', marginBottom: DROPDOWN_GAP, marginTop: 0 }
                : { top: '100%', marginTop: DROPDOWN_GAP }),
              maxHeight,
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
                onClick={() => onChange([])}
                style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: '0.8rem' }}
              >
                Clear
              </button>
              <button
                type="button"
                onClick={() => onChange(events.map((e) => e.event_id))}
                style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: '0.8rem' }}
              >
                Select all
              </button>
            </div>
            {events.map((e) => (
              <label
                key={e.event_id}
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
                  checked={selectedIds.includes(e.event_id)}
                  onChange={() => toggleEvent(e.event_id)}
                  style={{ flexShrink: 0 }}
                />
                <span style={{ fontSize: '0.9rem', wordBreak: 'break-word' }}>
                  {e.event_name} ({e.date})
                </span>
              </label>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
