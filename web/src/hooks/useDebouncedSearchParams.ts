import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

const DEFAULT_DEBOUNCE_MS = 300

export interface UseDebouncedSearchParamsOptions {
  /** Query param keys to manage. Values are read from and written to the URL. */
  keys: string[]
  /** Debounce delay before updating the URL. Default 300ms. */
  debounceMs?: number
}

export interface UseDebouncedSearchParamsResult {
  /** Current filter values (one per key). Use for controlled inputs. */
  filters: Record<string, string>
  /** Update one filter; empty string or null removes the param. Resets `page` when the URL is updated. */
  setFilter: (key: string, value: string | null) => void
}

/**
 * Keeps a set of query params in sync with local state and updates the URL after a debounce.
 * When the URL changes externally (e.g. back/forward), local state is synced from the URL.
 * Updating any filter removes the `page` param so pagination resets.
 */
export function useDebouncedSearchParams(
  options: UseDebouncedSearchParamsOptions
): UseDebouncedSearchParamsResult {
  const { keys, debounceMs = DEFAULT_DEBOUNCE_MS } = options
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const searchParamsRef = useRef(searchParams)
  searchParamsRef.current = searchParams

  const urlSnapshot = keys.map((k) => searchParams.get(k) ?? '').join('\0')
  const [filterValues, setFilterValues] = useState<Record<string, string>>(() =>
    keys.reduce((acc, k) => ({ ...acc, [k]: searchParams.get(k) ?? '' }), {})
  )

  // Sync local state from URL when URL changes (e.g. back/forward)
  useEffect(() => {
    const next = keys.reduce(
      (acc, k) => ({ ...acc, [k]: searchParams.get(k) ?? '' }),
      {} as Record<string, string>
    )
    setFilterValues((prev) =>
      keys.every((k) => prev[k] === next[k]) ? prev : next
    )
  }, [urlSnapshot, keys.join(',')])

  // Debounced URL update when filter values change
  useEffect(() => {
    const t = setTimeout(() => {
      const params = new URLSearchParams(searchParamsRef.current)
      keys.forEach((k) => {
        const v = filterValues[k]
        if (v != null && v !== '') params.set(k, v)
        else params.delete(k)
      })
      params.delete('page')
      const next = params.toString()
      if (next !== searchParamsRef.current.toString()) {
        navigate({ search: next }, { replace: true })
      }
    }, debounceMs)
    return () => clearTimeout(t)
  }, [filterValues, debounceMs, keys.join(','), navigate])

  const setFilter = (key: string, value: string | null) => {
    setFilterValues((prev) => ({
      ...prev,
      [key]: value ?? '',
    }))
  }

  return {
    filters: filterValues,
    setFilter,
  }
}
