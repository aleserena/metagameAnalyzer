// After a deploy the hashed chunk files of the previous build are gone. A tab
// opened before the deploy still runs the old index-*.js, so the first lazy
// route it visits asks for a chunk that now 404s ("Failed to fetch dynamically
// imported module"). Reloading picks up the new index.html and its chunks.

const RELOAD_KEY = 'chunkReloadAt'
// A second chunk failure within this window means the reload did not help
// (chunk really missing, offline, ...): surface the error instead of looping.
const RELOAD_WINDOW_MS = 30_000

const CHUNK_ERROR_RE =
  /Failed to fetch dynamically imported module|error loading dynamically imported module|Importing a module script failed|Unable to preload CSS/i

export function isChunkLoadError(err: unknown): boolean {
  if (!err) return false
  const message = err instanceof Error ? err.message : String(err)
  return CHUNK_ERROR_RE.test(message)
}

const defaultReload = () => window.location.reload()

/** Reload the page unless we already did so moments ago. Returns whether it reloaded. */
export function reloadOnceForNewBuild(reload: () => void = defaultReload): boolean {
  const now = Date.now()
  try {
    const last = Number(sessionStorage.getItem(RELOAD_KEY) || 0)
    if (now - last < RELOAD_WINDOW_MS) return false
    sessionStorage.setItem(RELOAD_KEY, String(now))
  } catch {
    // Storage unavailable: still reload once; worst case the user sees the error after it.
  }
  reload()
  return true
}

/**
 * Wrap a dynamic import for React.lazy: on a missing-chunk error, reload the
 * page (keeping the Suspense fallback on screen) instead of failing.
 */
export function importWithReload<T>(factory: () => Promise<T>, reload: () => void = defaultReload): Promise<T> {
  return factory().catch((err: unknown) => {
    if (isChunkLoadError(err) && reloadOnceForNewBuild(reload)) {
      return new Promise<T>(() => {})
    }
    throw err
  })
}
