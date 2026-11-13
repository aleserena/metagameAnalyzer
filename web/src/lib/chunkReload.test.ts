import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { isChunkLoadError, reloadOnceForNewBuild, importWithReload } from './chunkReload'

describe('isChunkLoadError', () => {
  it.each([
    'Failed to fetch dynamically imported module: https://x/assets/Events-CmWtiSYD.js', // Chrome
    'error loading dynamically imported module: https://x/assets/Events-CmWtiSYD.js', // Firefox
    'Importing a module script failed.', // Safari
    'Unable to preload CSS for /assets/Events-abc.css', // Vite CSS preload
  ])('recognises %s', (message) => {
    expect(isChunkLoadError(new TypeError(message))).toBe(true)
  })

  it('ignores ordinary errors', () => {
    expect(isChunkLoadError(new Error('Cannot read properties of undefined'))).toBe(false)
    expect(isChunkLoadError(null)).toBe(false)
  })
})

describe('reloadOnceForNewBuild', () => {
  const reload = vi.fn()

  beforeEach(() => {
    sessionStorage.clear()
    reload.mockReset()
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-13T20:00:00Z'))
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('reloads the first time', () => {
    expect(reloadOnceForNewBuild(reload)).toBe(true)
    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('does not reload again straight after a reload (avoids a loop when the chunk is really gone)', () => {
    reloadOnceForNewBuild(reload)
    vi.advanceTimersByTime(5_000)
    expect(reloadOnceForNewBuild(reload)).toBe(false)
    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('reloads again for a later deploy', () => {
    reloadOnceForNewBuild(reload)
    vi.advanceTimersByTime(60_000)
    expect(reloadOnceForNewBuild(reload)).toBe(true)
    expect(reload).toHaveBeenCalledTimes(2)
  })
})

describe('importWithReload', () => {
  beforeEach(() => sessionStorage.clear())

  it('passes a successful import through', async () => {
    const mod = { default: () => null }
    await expect(importWithReload(() => Promise.resolve(mod), vi.fn())).resolves.toBe(mod)
  })

  it('reloads and stays pending when a chunk is missing', async () => {
    const reload = vi.fn()
    const p = importWithReload(
      () => Promise.reject(new TypeError('Failed to fetch dynamically imported module: /assets/x.js')),
      reload,
    )
    const settled = await Promise.race([p.then(() => 'settled', () => 'settled'), new Promise((r) => setTimeout(() => r('pending'), 20))])
    expect(settled).toBe('pending')
    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('rethrows when it already reloaded', async () => {
    const reload = vi.fn()
    reloadOnceForNewBuild(reload)
    const err = new TypeError('Failed to fetch dynamically imported module: /assets/x.js')
    await expect(importWithReload(() => Promise.reject(err), reload)).rejects.toBe(err)
  })

  it('rethrows other errors without reloading', async () => {
    const reload = vi.fn()
    const err = new Error('boom')
    await expect(importWithReload(() => Promise.reject(err), reload)).rejects.toBe(err)
    expect(reload).not.toHaveBeenCalled()
  })
})
