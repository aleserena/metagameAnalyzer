import { useState, useEffect, useRef } from 'react'
import { useBlocker } from 'react-router-dom'
import toast from 'react-hot-toast'
import { loadDecks, exportDecks } from '../api'
import { getToken } from '../contexts/AuthContext'
import { FORMATS, META_EDH } from '../config'

const FORMAT_OPTIONS = Object.entries(FORMATS)
const PERIOD_OPTIONS = Object.keys(META_EDH)

export default function Scrape() {
  const [format, setFormat] = useState('EDH')
  const [period, setPeriod] = useState('Last 2 Months')
  const [store, setStore] = useState('')
  const [eventIds, setEventIds] = useState('')
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState<string[]>([])
  const [pct, setPct] = useState(0)
  const [fileInput, setFileInput] = useState<HTMLInputElement | null>(null)
  const logRef = useRef<HTMLDivElement>(null)
  const blockerDialogRef = useRef<HTMLDivElement>(null)

  const blocker = useBlocker(loading)

  useEffect(() => {
    if (blocker.state === 'blocked' && blockerDialogRef.current) {
      const focusable = blockerDialogRef.current.querySelector<HTMLButtonElement>('button')
      focusable?.focus()
    }
  }, [blocker.state])

  // Block browser tab close/refresh while scraping
  useEffect(() => {
    if (!loading) return
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault()
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [loading])

  const handleScrape = async () => {
    setLoading(true)
    setProgress([])
    setPct(0)

    try {
      const token = getToken()
      const res = await fetch('/api/scrape', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          format,
          period: period || undefined,
          store: store || undefined,
          event_ids: eventIds || undefined,
        }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(err.detail || res.statusText)
      }

      const reader = res.body?.getReader()
      if (!reader) throw new Error('No response stream')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const data = JSON.parse(line.slice(6))
            if (data.type === 'progress') {
              setProgress((prev) => [...prev, data.message])
              setPct(data.pct ?? 0)
              setTimeout(() => logRef.current?.scrollTo(0, logRef.current.scrollHeight), 0)
            } else if (data.type === 'done') {
              toast.success(data.message)
              setPct(100)
            } else if (data.type === 'error') {
              toast.error(data.message)
            }
          } catch {
            // ignore malformed lines
          }
        }
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  const handleLoadFile = async () => {
    const input = fileInput
    if (!input?.files?.length) {
      toast.error('Select a file first')
      return
    }
    setLoading(true)
    try {
      const result = await loadDecks(input.files[0])
      toast.success(result.message)
      input.value = ''
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  const handleDownload = async () => {
    try {
      const blob = await exportDecks()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'decks.json'
      a.click()
      URL.revokeObjectURL(url)
      toast.success('Download started (decks.json)')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div>
      <h1 className="page-title">Scrape & Load Data</h1>

      <div
        className="scrape-sections-grid"
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '1.5rem',
          marginBottom: '1.5rem',
        }}
      >
        <div className="chart-container chart-container--compact">
          <h3 style={{ margin: '0 0 1rem' }}>Load from file</h3>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-end' }}>
            <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
              <label htmlFor="scrape-file-input">JSON file (decks.json)</label>
              <input
                id="scrape-file-input"
                type="file"
                accept=".json"
                ref={setFileInput}
                onChange={() => {}}
                aria-label="Select JSON file to load decks"
              />
            </div>
            <button className="btn" onClick={handleLoadFile} disabled={loading}>
              Load
            </button>
          </div>
        </div>

        <div className="chart-container chart-container--compact">
          <h3 style={{ margin: '0 0 1rem' }}>Download current data</h3>
          <p style={{ margin: '0 0 0.75rem', fontSize: '0.9rem', color: 'var(--text-muted)' }}>
            Export all loaded or scraped decks as JSON (same format as Load accepts).
          </p>
          <button className="btn" onClick={handleDownload} disabled={loading}>
            Download decks.json
          </button>
        </div>
      </div>

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
        <button className="btn" onClick={handleScrape} disabled={loading}>
          {loading ? 'Scraping...' : 'Run Scrape'}
        </button>

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

      {loading && (
        <div style={{ marginTop: '1rem', color: 'var(--warning)', fontSize: '0.875rem' }}>
          Scraping in progress. Please don't close or navigate away from this page.
        </div>
      )}

      {blocker.state === 'blocked' && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            zIndex: 10000,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
          aria-hidden="false"
        >
          <div
            ref={blockerDialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="scrape-blocker-title"
            aria-label="Leave page confirmation"
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: 12,
              padding: '2rem',
              maxWidth: 400,
              textAlign: 'center',
            }}
          >
            <p id="scrape-blocker-title" style={{ marginBottom: '1.5rem', fontSize: '1rem' }}>
              Scraping is in progress. Are you sure you want to leave?
            </p>
            <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center' }}>
              <button
                type="button"
                className="btn"
                onClick={() => blocker.reset?.()}
                aria-label="Stay on page"
              >
                Stay
              </button>
              <button
                type="button"
                className="btn"
                style={{ background: 'var(--danger, #e53e3e)' }}
                onClick={() => blocker.proceed?.()}
                aria-label="Leave page"
              >
                Leave
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
