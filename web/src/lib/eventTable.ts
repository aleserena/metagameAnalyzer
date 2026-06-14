/**
 * Shared helpers for event tables (Events list, Event detail).
 * Pure functions — no React, no DOM.
 */
import type { EventWithOrigin } from '../api'
import { dateSortKey } from '../utils'

/** Coerce a value to a display string; avoid rendering [object Object] or null. */
export function cellStr(v: unknown): string {
  if (v == null) return '—'
  if (typeof v === 'object') return '—'
  return String(v)
}

export type EventSortKey =
  | 'event_name'
  | 'date'
  | 'format_id'
  | 'player_count'
  | 'store'
  | 'location'

/** Sort key extractor for an event row: returns a comparable string/number per column. */
export function normalizeForSort(e: EventWithOrigin, key: EventSortKey): string | number {
  switch (key) {
    case 'event_name':
      return (typeof e.event_name === 'string' ? e.event_name : '') || 'Unnamed'
    case 'date':
      return dateSortKey(cellStr(e.date))
    case 'format_id':
      return cellStr(e.format_id)
    case 'player_count':
      return typeof e.player_count === 'number' ? e.player_count : 0
    case 'store':
      return cellStr(e.store)
    case 'location':
      return cellStr(e.location)
    default:
      return ''
  }
}
