import { useState, useEffect, useRef } from 'react'
import { useBlocker } from 'react-router-dom'
import { loadDecks } from '../api'
import { FORMATS, META_EDH } from '../config'

const FORMAT_OPTIONS = Object.entries(FORMATS)
const PERIOD_OPTIONS = Object.keys(META_EDH)

export default function Scrape() {
  const [format, setFormat] = useState('EDH')
  const [period, setPeriod] = useState('Last 2 Months')
  const [store, setStore] = useState('')
  const [eventIds, setEventIds] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [progress, setProgress] = useState<string[]>([])
  const [pct, setPct] = useState(0)
  const [fileInput, setFileInput] = useState<HTMLInputElement | null>(null)
  const logRef = useRef<HTMLDivElement>(null)

  const blocker = useBlocker(loading)

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
    setError(null)
    setMessage(null)
    setProgress([])
    setPct(0)

    try {
      const res = await fetch('/api/scrape', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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
              setMessage(data.message)
              setPct(100)
            } else if (data.type === 'error') {
              setError(data.message)
            }
          } catch {
            // ignore malformed lines
          }
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  const handleLoadFile = async () => {
    const input = fileInput
    if (!input?.files?.length) {
      setError('Select a file first')
      return
    }
    setLoading(true)
    setError(null)
    setMessage(null)
    try {
      const result = await loadDecks(input.files[0])
      setMessage(result.message)
      input.value = ''
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h1 className="page-title">Scrape & Load Data</h1>

      <div className="chart-container" style={{ maxWidth: 500 }}>
        <h3 style={{ margin: '0 0 1rem' }}>Load from file</h3>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-end' }}>
          <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
            <label>JSON file (decks.json)</label>
            <input
              type="file"
              accept=".json"
              ref={setFileInput}
              onChange={() => {}}
            />
          </div>
          <button className="btn" onClick={handleLoadFile} disabled={loading}>
            Load
          </button>
        </div>
      </div>

      <div className="chart-container" style={{ maxWidth: 500, marginTop: '1.5rem' }}>
        <h3 style={{ margin: '0 0 1rem' }}>Scrape from MTGTop8</h3>
        <div className="form-group">
          <label>Format</label>
          <select value={format} onChange={(e) => setFormat(e.target.value)}>
            {FORMAT_OPTIONS.map(([id, name]) => (
              <option key={id} value={id}>{name}</option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label>Time period</label>
          <select value={period} onChange={(e) => setPeriod(e.target.value)}>
            {PERIOD_OPTIONS.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label>Store filter (substring in event name)</label>
          <input
            type="text"
            placeholder="e.g. Hadouken, Angers"
            value={store}
            onChange={(e) => setStore(e.target.value)}
          />
        </div>
        <div className="form-group">
          <label>Event IDs (comma-separated, optional)</label>
          <input
            type="text"
            placeholder="e.g. 80455,80480"
            value={eventIds}
            onChange={(e) => setEventIds(e.target.value)}
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

      {error && <div className="error" style={{ marginTop: '1rem' }}>{error}</div>}
      {message && <div style={{ marginTop: '1rem', color: 'var(--success)', fontWeight: 600 }}>{message}</div>}
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
        >
          <div
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: 12,
              padding: '2rem',
              maxWidth: 400,
              textAlign: 'center',
            }}
          >
            <p style={{ marginBottom: '1.5rem', fontSize: '1rem' }}>
              Scraping is in progress. Are you sure you want to leave?
            </p>
            <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center' }}>
              <button className="btn" onClick={() => blocker.reset?.()}>
                Stay
              </button>
              <button
                className="btn"
                style={{ background: 'var(--danger, #e53e3e)' }}
                onClick={() => blocker.proceed?.()}
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
