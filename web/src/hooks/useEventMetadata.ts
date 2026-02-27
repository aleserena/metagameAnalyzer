import { useCallback, useEffect, useState } from 'react'
import { getEvents, getDateRange } from '../api'
import type { Event } from '../types'

export interface UseEventMetadataResult {
  events: Event[]
  maxDate: string | null
  lastEventDate: string | null
  loading: boolean
  error: string | null
  refetch: () => void
}

/**
 * Fetches events and date-range metadata from the API. Use on pages that need
 * event lists and/or date presets (e.g. Decks, Dashboard, Metagame). Does not
 * show toasts; callers should react to `error` and display messages as needed.
 */
export function useEventMetadata(): UseEventMetadataResult {
  const [events, setEvents] = useState<Event[]>([])
  const [maxDate, setMaxDate] = useState<string | null>(null)
  const [lastEventDate, setLastEventDate] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refetch = useCallback(() => {
    setLoading(true)
    setError(null)
    Promise.all([getEvents(), getDateRange()])
      .then(([eventsRes, rangeRes]) => {
        setEvents(eventsRes.events)
        setMaxDate(rangeRes.max_date)
        setLastEventDate(rangeRes.last_event_date)
        setError(null)
      })
      .catch((e) => {
        const msg = e instanceof Error ? e.message : String(e ?? '')
        setError(msg)
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    refetch()
  }, [refetch])

  return {
    events,
    maxDate,
    lastEventDate,
    loading,
    error,
    refetch,
  }
}
