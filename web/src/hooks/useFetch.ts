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
  const requestIdRef = useRef(0)

  const run = useCallback(() => {
    const id = ++requestIdRef.current
    setLoading(true)
    setError(null)
    fetcherRef.current()
      .then((result) => {
        if (id !== requestIdRef.current) return
        setData(result)
        setError(null)
      })
      .catch((e) => {
        if (id !== requestIdRef.current) return
        const msg = e instanceof Error ? e.message : String(e ?? '')
        setError(msg)
        setData(null)
      })
      .finally(() => {
        if (id !== requestIdRef.current) return
        setLoading(false)
      })
  }, [])

  useEffect(() => {
    run()
  }, [run, ...deps])

  return { data, loading, error, refetch: run }
}
