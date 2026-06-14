import { describe, expect, it } from 'vitest'
import type { EventWithOrigin } from '../api'
import { cellStr, normalizeForSort } from './eventTable'

describe('cellStr', () => {
  it('renders em dash for null/undefined', () => {
    expect(cellStr(null)).toBe('—')
    expect(cellStr(undefined)).toBe('—')
  })

  it('renders em dash for objects (avoids [object Object])', () => {
    expect(cellStr({})).toBe('—')
    expect(cellStr([1, 2])).toBe('—')
  })

  it('stringifies primitives', () => {
    expect(cellStr('Angers')).toBe('Angers')
    expect(cellStr(42)).toBe('42')
    expect(cellStr(0)).toBe('0')
    expect(cellStr(false)).toBe('false')
  })
})

describe('normalizeForSort', () => {
  const ev = (over: Partial<EventWithOrigin>): EventWithOrigin =>
    ({ event_name: '', date: '', format_id: '', store: '', location: '', ...over }) as EventWithOrigin

  it('falls back to "Unnamed" for empty event_name', () => {
    expect(normalizeForSort(ev({ event_name: '' }), 'event_name')).toBe('Unnamed')
    expect(normalizeForSort(ev({ event_name: 'GP Lyon' }), 'event_name')).toBe('GP Lyon')
  })

  it('returns a sortable date key (YYMMDD)', () => {
    expect(normalizeForSort(ev({ date: '01/02/26' }), 'date')).toBe('260201')
  })

  it('returns numeric player_count, defaulting to 0', () => {
    expect(normalizeForSort(ev({ player_count: 32 }), 'player_count')).toBe(32)
    expect(normalizeForSort(ev({ player_count: undefined }), 'player_count')).toBe(0)
  })

  it('coerces store/location/format via cellStr', () => {
    expect(normalizeForSort(ev({ store: 'Le Vizz' }), 'store')).toBe('Le Vizz')
    expect(normalizeForSort(ev({ location: null as unknown as string }), 'location')).toBe('—')
    expect(normalizeForSort(ev({ format_id: 'EDH' }), 'format_id')).toBe('EDH')
  })
})
