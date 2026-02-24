import { useCallback, useEffect, useRef, useState } from 'react'

export interface UseFetchResult<T> {
  data: T | null
  loading: boolean
  error: string | null
  refetch: () => void
}

/**
 * Fetches data when deps change. Returns { data, loading, error, refetch }.
 * Clears error on refetch. Use in detail/list pages for consistent loading/error handling.
 */
export function useFetch<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = []
): UseFetchResult<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  const run = useCallback(() => {
    setLoading(true)
    setError(null)
    fetcherRef.current()
      .then((result) => {
        setData(result)
        setError(null)
      })
      .catch((e) => {
        const msg = e instanceof Error ? e.message : String(e ?? '')
        setError(msg)
        setData(null)
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    run()
  }, [run, ...deps])

  return { data, loading, error, refetch: run }
}
