import { useState, useEffect, useRef, useCallback } from 'react'
import toast from 'react-hot-toast'
import { getScrapeStatus, startScrape, stopScrape } from '../api'
import { reportError } from '../utils'
import { FORMATS, META_EDH } from '../config'
import type { ScrapeFailedDeck, ScrapeJobSnapshot } from '../types'

const FORMAT_OPTIONS = Object.entries(FORMATS)
const PERIOD_OPTIONS = Object.keys(META_EDH)
const POLL_MS = 1500

export default function Scrape() {
  const [format, setFormat] = useState('EDH')
  const [period, setPeriod] = useState('Last 2 Months')
  const [store, setStore] = useState('')
  const [eventIds, setEventIds] = useState('')
  const [forceReplace, setForceReplace] = useState(false)
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState<string[]>([])
  const [pct, setPct] = useState(0)
  const [errors, setErrors] = useState<string[]>([])
  const [failedDecks, setFailedDecks] = useState<ScrapeFailedDeck[]>([])
  const logRef = useRef<HTMLDivElement>(null)
  const jobIdRef = useRef<string | null>(null)
  const afterRef = useRef(0)
  const wasRunningRef = useRef(false)
  const mountedRef = useRef(true)
  const inFlightRef = useRef(false)
  const failedPollsRef = useRef(0)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const goIdle = useCallback((message: string) => {
    wasRunningRef.current = false
    jobIdRef.current = null
    afterRef.current = 0
    setLoading(false)
    toast(message)
  }, [])

  const applySnapshot = useCallback((job: ScrapeJobSnapshot, requestedAfter: number) => {
    jobIdRef.current = job.id
    afterRef.current = job.next
    if (job.messages.length > 0 || requestedAfter === 0) {
      setProgress((prev) => (requestedAfter === 0 ? job.messages : [...prev, ...job.messages]))
      setTimeout(() => logRef.current?.scrollTo?.(0, logRef.current.scrollHeight), 0)
    }
    setPct(job.pct)
    setFailedDecks(job.failed_decks)
    if (job.status === 'running') {
      wasRunningRef.current = true
      setLoading(true)
      return
    }
    setLoading(false)
    if (job.status === 'error') setErrors([job.message])
    if (wasRunningRef.current) {
      if (job.status === 'done') toast.success(job.message)
      else if (job.status === 'cancelled') toast(job.message, { icon: '⏹' })
      else toast.error(job.message)
    }
    wasRunningRef.current = false
  }, [])

  const poll = useCallback(async () => {
    const requestedAfter = afterRef.current
    try {
      const { job } = await getScrapeStatus(requestedAfter)
      if (!mountedRef.current) return
      failedPollsRef.current = 0
      if (!job) {
        if (wasRunningRef.current) goIdle('The scrape is no longer running on the server.')
        else setLoading(false)
        return
      }
      if (jobIdRef.current && jobIdRef.current !== job.id) {
        // A different job than the one we were following: reload its log from the start.
        afterRef.current = 0
        jobIdRef.current = job.id
        void poll()
        return
      }
      applySnapshot(job, requestedAfter)
    } catch {
      if (!mountedRef.current) return
      if (!wasRunningRef.current) {
        setLoading(false)
        return
      }
      // A single failed poll says nothing about the job; give up only after repeated failures.
      failedPollsRef.current += 1
      if (failedPollsRef.current >= 3) {
        failedPollsRef.current = 0
        goIdle('Lost contact with the server. Reload the page to check the scrape.')
      }
    }
  }, [applySnapshot, goIdle])

  // Reattach to a scrape already running on the server (or show the last result).
  useEffect(() => {
    void poll()
  }, [poll])

  // While a scrape runs, keep polling the server.
  useEffect(() => {
    if (!loading) return
    const timer = setInterval(() => {
      if (inFlightRef.current) return
      inFlightRef.current = true
      poll().finally(() => {
        inFlightRef.current = false
      })
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [loading, poll])

  const handleScrape = async () => {
    setLoading(true)
    setProgress([])
    setPct(0)
    setErrors([])
    setFailedDecks([])
    jobIdRef.current = null
    afterRef.current = 0
    try {
      const { job } = await startScrape({
        format,
        period: period || undefined,
        store: store || undefined,
        event_ids: eventIds || undefined,
        ...(forceReplace ? { force_replace: true } : {}),
      })
      wasRunningRef.current = true
      applySnapshot(job, 0)
    } catch (e) {
      const errMsg = reportError(e)
      setErrors([errMsg])
      toast.error(errMsg)
      wasRunningRef.current = false
      // A scrape may already be running (409): follow it instead of showing a dead form.
      void poll()
      setLoading(false)
    }
  }

  return (
    <div>
      <h1 className="page-title">Scrape</h1>

      <div className="chart-container chart-container--compact" style={{ maxWidth: 500 }}>
        <h3 style={{ margin: '0 0 1rem' }}>Scrape from MTGTop8</h3>
        <div className="form-group">
          <label htmlFor="scrape-format">Format</label>
          <select id="scrape-format" value={format} onChange={(e) => setFormat(e.target.value)} aria-label="Scrape format">
            {FORMAT_OPTIONS.map(([id, name]) => (
              <option key={id} value={id}>{name}</option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label htmlFor="scrape-period">Time period</label>
          <select id="scrape-period" value={period} onChange={(e) => setPeriod(e.target.value)} aria-label="Time period">
            {PERIOD_OPTIONS.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label htmlFor="scrape-store">Store filter (substring in event name)</label>
          <input
            id="scrape-store"
            type="text"
            placeholder="e.g. Hadouken, Angers"
            value={store}
            onChange={(e) => setStore(e.target.value)}
            aria-label="Store filter"
          />
        </div>
        <div className="form-group">
          <label htmlFor="scrape-event-ids">Event IDs (comma-separated, optional)</label>
          <input
            id="scrape-event-ids"
            type="text"
            placeholder="e.g. 80455,80480"
            value={eventIds}
            onChange={(e) => setEventIds(e.target.value)}
            aria-label="Event IDs"
          />
        </div>
        <div className="form-group" style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
            <input
              id="scrape-force-replace"
              type="checkbox"
              checked={forceReplace}
              onChange={(e) => setForceReplace(e.target.checked)}
              aria-label="Force replace existing events"
            />
            Force replace existing events
          </label>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Re-scrape and refresh MTGTop8 events. Existing decks are updated in place; recorded results and manual decks are kept.
          </span>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          <button className="btn" onClick={handleScrape} disabled={loading}>
            {loading ? 'Scraping...' : 'Run Scrape'}
          </button>
          {loading && (
            <button
              type="button"
              className="btn"
              style={{ background: 'var(--danger, #e53e3e)' }}
              onClick={() => {
                stopScrape().catch(() => {})
              }}
            >
              Stop
            </button>
          )}
        </div>

        {loading && (
          <div style={{ marginTop: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem', fontSize: '0.875rem' }}>
              <span>Progress</span>
              <span>{Math.round(pct)}%</span>
            </div>
            <div style={{ width: '100%', height: 8, background: 'var(--border)', borderRadius: 4, overflow: 'hidden' }}>
              <div
                style={{
                  height: '100%',
                  width: `${pct}%`,
                  background: 'var(--accent)',
                  borderRadius: 4,
                  transition: 'width 0.3s ease',
                }}
              />
            </div>
          </div>
        )}
      </div>

      {progress.length > 0 && (
        <div
          ref={logRef}
          style={{
            marginTop: '1rem',
            maxHeight: 250,
            overflow: 'auto',
            fontFamily: 'monospace',
            fontSize: '0.8rem',
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            borderRadius: 8,
            padding: '0.75rem',
          }}
        >
          {progress.map((p, i) => (
            <div key={i} style={{ padding: '0.1rem 0', color: 'var(--text-muted)' }}>{p}</div>
          ))}
        </div>
      )}

      {errors.length > 0 && (
        <div
          style={{
            marginTop: '1rem',
            padding: '0.75rem 1rem',
            background: 'rgba(229, 62, 62, 0.1)',
            border: '1px solid var(--danger, #e53e3e)',
            borderRadius: 8,
            fontSize: '0.875rem',
          }}
          role="alert"
        >
          <strong style={{ display: 'block', marginBottom: '0.5rem' }}>Errors</strong>
          <ul style={{ margin: 0, paddingLeft: '1.25rem' }}>
            {errors.map((err, i) => (
              <li key={i} style={{ marginBottom: '0.25rem', wordBreak: 'break-word' }}>{err}</li>
            ))}
          </ul>
        </div>
      )}

      {failedDecks.length > 0 && (
        <div
          style={{
            marginTop: '1rem',
            padding: '0.75rem 1rem',
            background: 'rgba(229, 62, 62, 0.1)',
            border: '1px solid var(--danger, #e53e3e)',
            borderRadius: 8,
            fontSize: '0.875rem',
          }}
          role="alert"
        >
          <strong style={{ display: 'block', marginBottom: '0.5rem' }}>
            {failedDecks.length} deck{failedDecks.length !== 1 ? 's' : ''} failed
          </strong>
          <ul style={{ margin: 0, paddingLeft: '1.25rem' }}>
            {failedDecks.map((f, i) => (
              <li key={i} style={{ marginBottom: '0.25rem', wordBreak: 'break-word' }}>
                Event {f.event_id ?? '?'}, deck {f.deck_id}: {f.error}
              </li>
            ))}
          </ul>
        </div>
      )}

      {loading && (
        <div style={{ marginTop: '1rem', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
          Scraping runs on the server. You can leave this page and come back; progress and results are kept.
        </div>
      )}
    </div>
  )
}
