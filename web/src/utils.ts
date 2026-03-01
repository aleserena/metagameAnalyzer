const GENERIC_ERROR_MESSAGE = 'There was an issue with the application, please refresh the page'

/** Default request timeout (ms). Used by API and auth fetches. */
export const REQUEST_TIMEOUT_MS = 30_000

/**
 * Normalize string for accent-insensitive substring matching (e.g. "matias" matches "Matías").
 * Lowercases and strips combining marks (NFD then remove \p{M}).
 */
export function normalizeSearchForFilter(s: string): string {
  if (!s || typeof s !== 'string') return ''
  return s
    .toLowerCase()
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
}

/** Longer timeout for initial page load (backend may be cold-starting). */
export const REQUEST_TIMEOUT_LOAD_MS = 60_000

/**
 * fetch with a timeout. Aborts the request after timeoutMs and throws a clear Error.
 * Use for all API requests so the UI never hangs indefinitely.
 */
export async function fetchWithTimeout(
  url: string,
  options: RequestInit & { timeoutMs?: number } = {}
): Promise<Response> {
  const { timeoutMs = REQUEST_TIMEOUT_MS, ...fetchOptions } = options
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(url, { ...fetchOptions, signal: controller.signal })
  } catch (e) {
    if (e instanceof Error && e.name === 'AbortError') {
      throw new Error('Request timed out. Check your connection or try again.', { cause: e })
    }
    throw e
  } finally {
    clearTimeout(timeoutId)
  }
}

const GENERIC_ERROR_PHRASES = new Set([
  '',
  'error',
  'unknown error',
  'internal server error',
  'bad gateway',
  'service unavailable',
  'failed to fetch',
  'networkerror when attempting to fetch resource',
  'load failed',
  'gateway timeout',
  'network request failed',
  'timeout',
  'request timeout',
  'not found',
])

/**
 * Returns a user-facing error message. For generic/unknown errors, returns a friendly message
 * asking the user to refresh the page.
 */
export function getErrorMessage(e: unknown): string {
  const msg = (e instanceof Error ? e.message : String(e ?? '')).trim()
  if (!msg || GENERIC_ERROR_PHRASES.has(msg.toLowerCase())) {
    return GENERIC_ERROR_MESSAGE
  }
  return msg
}

/**
 * Logs the error to the console and returns a user-facing message. Use in catch blocks
 * before showing a toast so the real error is available for debugging.
 */
export function reportError(e: unknown): string {
  console.error('[App error]', e)
  return getErrorMessage(e)
}

/** Parse DD/MM/YY to sortable key (YYMMDD) for comparison */
export function dateSortKey(ddMmYy: string): string {
  const [d, m, y] = ddMmYy.split('/').map(Number)
  const yy = String(y < 100 ? 2000 + y : y).slice(-2)
  const mm = String(m || 0).padStart(2, '0')
  const dd = String(d || 0).padStart(2, '0')
  return yy + mm + dd
}

/** Check if date (DD/MM/YY) is within [from, to] inclusive */
export function dateInRange(date: string, from: string | null, to: string | null): boolean {
  if (!from && !to) return true
  const key = dateSortKey(date)
  if (!/^\d{6}$/.test(key)) return true
  const keyInt = parseInt(key, 10)
  if (from) {
    const fromKey = dateSortKey(from)
    if (/^\d{6}$/.test(fromKey) && keyInt < parseInt(fromKey, 10)) return false
  }
  if (to) {
    const toKey = dateSortKey(to)
    if (/^\d{6}$/.test(toKey) && keyInt > parseInt(toKey, 10)) return false
  }
  return true
}

/** Parse DD/MM/YY to Date; subtract days; return DD/MM/YY */
export function dateMinusDays(ddMmYy: string, days: number): string {
  const [d, m, y] = ddMmYy.split('/').map(Number)
  const year = y < 100 ? 2000 + y : y
  const date = new Date(year, m - 1, d)
  date.setDate(date.getDate() - days)
  const dd = String(date.getDate()).padStart(2, '0')
  const mm = String(date.getMonth() + 1).padStart(2, '0')
  const yy = String(date.getFullYear()).slice(-2)
  return `${dd}/${mm}/${yy}`
}

/** Return first day of year for a given DD/MM/YY (as 01/01/YY) */
export function firstDayOfYear(ddMmYy: string): string {
  const [, , y] = ddMmYy.split('/').map(Number)
  const yy = String(y < 100 ? 2000 + y : y).slice(-2)
  return `01/01/${yy}`
}

/** Date range preset identifier used across EventSelector, Players, DeckDetail */
export type DatePreset = 'all' | '2weeks' | 'month' | '2months' | '6months' | 'thisYear' | 'lastEvent'

/**
 * Return dateFrom/dateTo (DD/MM/YY) for a preset. Use for date-range filters and event filtering.
 * - all: null, null
 * - lastEvent: lastEventDate, lastEventDate (when lastEventDate is set)
 * - others: from = computed from maxDate, to = maxDate
 */
export function getDateRangeFromPreset(
  maxDate: string | null,
  lastEventDate: string | null,
  preset: DatePreset
): { dateFrom: string | null; dateTo: string | null } {
  if (preset === 'all' || !maxDate) {
    return { dateFrom: null, dateTo: null }
  }
  if (preset === 'lastEvent' && lastEventDate) {
    return { dateFrom: lastEventDate, dateTo: lastEventDate }
  }
  const dateTo = maxDate
  const dateFrom =
    preset === '2weeks'
      ? dateMinusDays(maxDate, 14)
      : preset === 'month'
        ? dateMinusDays(maxDate, 30)
        : preset === '2months'
          ? dateMinusDays(maxDate, 60)
          : preset === '6months'
            ? dateMinusDays(maxDate, 183)
            : preset === 'thisYear'
              ? firstDayOfYear(maxDate)
              : maxDate
  return { dateFrom, dateTo }
}

/** Convert DD/MM/YY to YYYY-MM-DD for use with input type="date". Returns '' if invalid. */
export function ddMmYyToIso(ddMmYy: string): string {
  const t = ddMmYy.trim()
  if (!t) return ''
  const parts = t.split('/').map(Number)
  const [d, m, y] = parts
  if (!d || !m) return ''
  const year = (y < 100 ? 2000 + y : y)
  const date = new Date(year, m - 1, d)
  if (isNaN(date.getTime()) || date.getFullYear() !== year || date.getMonth() !== m - 1 || date.getDate() !== d) return ''
  const yy = String(date.getFullYear())
  const mm = String(date.getMonth() + 1).padStart(2, '0')
  const dd = String(date.getDate()).padStart(2, '0')
  return `${yy}-${mm}-${dd}`
}

/** Convert YYYY-MM-DD (from input type="date") to DD/MM/YY. Returns '' if invalid. */
export function isoToDdMmYy(iso: string): string {
  const t = iso.trim()
  if (!t) return ''
  const [y, m, d] = t.split('-').map(Number)
  if (!y || !m || !d) return ''
  const date = new Date(y, m - 1, d)
  if (isNaN(date.getTime()) || date.getFullYear() !== y || date.getMonth() !== m - 1 || date.getDate() !== d) return ''
  const yy = String(y).slice(-2)
  const mm = String(m).padStart(2, '0')
  const dd = String(d).padStart(2, '0')
  return `${dd}/${mm}/${yy}`
}

const PLURAL_MAP: Record<string, string> = {
  Sorcery: 'Sorceries',
  Other: 'Other',
}

export function pluralizeType(name: string): string {
  return PLURAL_MAP[name] ?? `${name}s`
}
