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
    Promise.allSettled([getEvents(), getDateRange()])
      .then(([eventsResult, rangeResult]) => {
        let nextError: string | null = null

        if (eventsResult.status === 'fulfilled') {
          setEvents(eventsResult.value.events)
        } else {
          setEvents([])
          nextError = eventsResult.reason instanceof Error ? eventsResult.reason.message : String(eventsResult.reason ?? '')
        }

        if (rangeResult.status === 'fulfilled') {
          setMaxDate(rangeResult.value.max_date)
          setLastEventDate(rangeResult.value.last_event_date)
        } else {
          setMaxDate(null)
          setLastEventDate(null)
          if (!nextError) {
            nextError = rangeResult.reason instanceof Error ? rangeResult.reason.message : String(rangeResult.reason ?? '')
          }
        }

        setError(nextError)
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
