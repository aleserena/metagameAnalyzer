import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import {
  getEvents,
  createEvent,
  getEventIdsWithDiscrepancies,
  getMergePreview,
  mergeEvents,
} from '../api'
import type { EventWithOrigin } from '../api'
import type { MergePreviewResponse, PlayerMergePair } from '../api'
import { useAuth } from '../contexts/AuthContext'
import { useFetch } from '../hooks/useFetch'
import { reportError, dateSortKey, ddMmYyToIso, isoToDdMmYy } from '../utils'

/** Coerce value to a string for display; avoid rendering [object Object]. */
function cellStr(v: unknown): string {
  if (v == null) return '—'
  if (typeof v === 'object') return '—'
  return String(v)
}

type SortKey = 'event_name' | 'date' | 'format_id' | 'player_count' | 'store' | 'location'

function normalizeForSort(e: EventWithOrigin, key: SortKey): string | number {
  switch (key) {
    case 'event_name':
      return (typeof e.event_name === 'string' ? e.event_name : '') || 'Unnamed'
    case 'date':
      return dateSortKey(cellStr(e.date))
    case 'format_id':
      return cellStr(e.format_id)
    case 'player_count':
      return typeof e.player_count === 'number' ? e.player_count : 0
    case 'store':
      return cellStr(e.store)
    case 'location':
      return cellStr(e.location)
    default:
      return ''
  }
}

export default function Events() {
  const { user } = useAuth()
  const { data, loading, error, refetch } = useFetch<{ events: EventWithOrigin[] }>(() => getEvents().then((r) => ({ events: r.events })), [])
  const events = data?.events ?? []
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [newStore, setNewStore] = useState('')
  const [newLocation, setNewLocation] = useState('')
  const [newDate, setNewDate] = useState('')
  const [newFormatId, setNewFormatId] = useState('EDH')
  const [newPlayerCount, setNewPlayerCount] = useState(0)
  const [filterName, setFilterName] = useState('')
  const [filterDateIso, setFilterDateIso] = useState('') // YYYY-MM-DD for date picker
  const [filterFormat, setFilterFormat] = useState('')
  const [filterWithDiscrepanciesOnly, setFilterWithDiscrepanciesOnly] = useState(false)
  const [sortBy, setSortBy] = useState<SortKey>('date')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const [mergeEventIdA, setMergeEventIdA] = useState('')
  const [mergeEventIdB, setMergeEventIdB] = useState('')
  const [mergePreview, setMergePreview] = useState<MergePreviewResponse | null>(null)
  const [mergeResolutions, setMergeResolutions] = useState<Record<string, 'keep' | 'remove'>>({})
  const [deckResolutions, setDeckResolutions] = useState<Record<string, Record<string, 'keep' | 'remove'>>>({})
  const [manualPairs, setManualPairs] = useState<PlayerMergePair[]>([])
  const [mergeLoading, setMergeLoading] = useState(false)
  const [mergeSubmitting, setMergeSubmitting] = useState(false)
  const { data: discrepancyData } = useFetch<{ event_ids: string[] }>(
    () => (user === 'admin' ? getEventIdsWithDiscrepancies() : Promise.resolve({ event_ids: [] })),
    [user]
  )
  const eventIdsWithDiscrepancies = useMemo(
    () => new Set((discrepancyData?.event_ids ?? []).map((id) => String(id))),
    [discrepancyData]
  )

  useEffect(() => {
    if (error) toast.error(reportError(new Error(error)))
  }, [error])

  const handleCreate = () => {
    const name = newName.trim() || 'Unnamed'
    const date = newDate.trim()
    const formatId = newFormatId.trim() || 'EDH'
    if (!newPlayerCount || newPlayerCount < 1) {
      toast.error('Number of players is required (at least 1).')
      return
    }
    setCreating(true)
    createEvent({
      event_name: name,
      date,
      format_id: formatId,
      player_count: newPlayerCount,
      store: newStore.trim(),
      location: newLocation.trim(),
    })
      .then(() => {
        refetch()
        setNewName('')
        setNewStore('')
        setNewLocation('')
        setNewDate('')
        setNewFormatId('EDH')
        setNewPlayerCount(0)
        refetch()
        toast.success('Event created')
      })
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setCreating(false))
  }

  const handleMergePreview = () => {
    const a = mergeEventIdA.trim()
    const b = mergeEventIdB.trim()
    if (!a || !b) {
      toast.error('Select both events to merge.')
      return
    }
    if (a === b) {
      toast.error('Select two different events.')
      return
    }
    setMergeLoading(true)
    setMergePreview(null)
    getMergePreview(a, b)
      .then((res) => {
        setMergePreview(res)
        setMergeResolutions({})
        setDeckResolutions({})
        setManualPairs([])
      })
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setMergeLoading(false))
  }

  const handleMergeConfirm = () => {
    if (!mergePreview?.can_merge) return
    setMergeSubmitting(true)
    mergeEvents({
      event_id_keep: mergePreview.keep_event_id,
      event_id_remove: mergePreview.remove_event_id,
      resolutions: mergeResolutions,
      player_merges: manualPairs.length > 0 ? manualPairs : undefined,
      deck_resolutions: Object.keys(deckResolutions).length > 0 ? deckResolutions : undefined,
    })
      .then((r) => {
        const parts: string[] = []
        if (r.decks_merged) parts.push(`${r.decks_merged} player(s) merged`)
        if (r.decks_moved) parts.push(`${r.decks_moved} deck(s) moved`)
        toast.success(parts.length ? `Events merged. ${parts.join('; ')}.` : 'Events merged.')
        setMergePreview(null)
        setMergeEventIdA('')
        setMergeEventIdB('')
        setMergeResolutions({})
        setDeckResolutions({})
        setManualPairs([])
        refetch()
      })
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setMergeSubmitting(false))
  }

  const mergeFieldLabel: Record<string, string> = {
    event_name: 'Event name',
    store: 'Store',
    location: 'Location',
    date: 'Date',
    format_id: 'Format',
    player_count: 'Players',
    player: 'Player name',
    name: 'Deck name',
    rank: 'Rank',
    commanders: 'Commanders',
    archetype: 'Archetype',
    mainboard: 'Mainboard',
    sideboard: 'Sideboard',
  }

  /** Format a conflict value for display (lists show length). */
  function conflictVal(v: unknown): string {
    if (v == null) return '—'
    if (Array.isArray(v)) return `${v.length} item(s)`
    return String(v)
  }

  const pairKey = (keepId: number, removeId: number) => `${keepId}-${removeId}`

  const addManualPair = (deckIdKeep: number, deckIdRemove: number) => {
    setManualPairs((prev) => {
      if (prev.some((p) => p.deck_id_remove === deckIdRemove)) return prev
      return [...prev, { deck_id_keep: deckIdKeep, deck_id_remove: deckIdRemove }]
    })
  }
  const removeManualPair = (deckIdRemove: number) => {
    setManualPairs((prev) => prev.filter((p) => p.deck_id_remove !== deckIdRemove))
  }
  const isManualPaired = (deckIdRemove: number) => manualPairs.some((p) => p.deck_id_remove === deckIdRemove)
  const getManualPairKeep = (deckIdRemove: number) => manualPairs.find((p) => p.deck_id_remove === deckIdRemove)?.deck_id_keep

  const filteredAndSorted = useMemo(() => {
    let list = events
    const nameLower = filterName.trim().toLowerCase()
    if (nameLower) {
      list = list.filter((e) =>
        (typeof e.event_name === 'string' ? e.event_name : '').toLowerCase().includes(nameLower)
      )
    }
    if (filterDateIso) {
      list = list.filter((e) => ddMmYyToIso(cellStr(e.date)) === filterDateIso)
    }
    if (filterFormat) {
      list = list.filter((e) => cellStr(e.format_id) === filterFormat)
    }
    if (user === 'admin' && filterWithDiscrepanciesOnly) {
      list = list.filter((e) => eventIdsWithDiscrepancies.has(String(e.event_id)))
    }
    const dir = sortOrder === 'asc' ? 1 : -1
    return [...list].sort((a, b) => {
      const va = normalizeForSort(a, sortBy)
      const vb = normalizeForSort(b, sortBy)
      const cmp = typeof va === 'number' && typeof vb === 'number'
        ? va - vb
        : String(va).localeCompare(String(vb), undefined, { numeric: true })
      return dir * cmp
    })
  }, [events, filterName, filterDateIso, filterFormat, filterWithDiscrepanciesOnly, eventIdsWithDiscrepancies, user, sortBy, sortOrder])

  const formatOptions = useMemo(() => {
    const set = new Set<string>()
    events.forEach((e) => {
      const f = cellStr(e.format_id).trim()
      if (f) set.add(f)
    })
    return [...set].sort()
  }, [events])

  const hasFilters = Boolean(filterName.trim() || filterDateIso || filterFormat || (user === 'admin' && filterWithDiscrepanciesOnly))
  const clearFilters = () => {
    setFilterName('')
    setFilterDateIso('')
    setFilterFormat('')
    setFilterWithDiscrepanciesOnly(false)
  }

  const handleSort = (key: SortKey) => {
    if (sortBy === key) {
      setSortOrder((o) => (o === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortBy(key)
      setSortOrder(key === 'date' ? 'desc' : 'asc')
    }
  }

  return (
    <div className="page">
      <h1 className="page-title">Events</h1>
      <p className="muted" style={{ marginBottom: '1.5rem' }}>
        All events. Click an event to see its decks and details.
      </p>

      {user === 'admin' && (
        <section className="card" style={{ marginBottom: '1.5rem' }}>
          <h2 style={{ marginTop: 0 }}>Create event</h2>
          <div className="toolbar toolbar--stack-on-mobile" style={{ gap: '0.75rem', alignItems: 'flex-end' }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span className="label">Name</span>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Event name"
                style={{ minWidth: 200 }}
              />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span className="label">Store</span>
              <input
                type="text"
                value={newStore}
                onChange={(e) => setNewStore(e.target.value)}
                placeholder="Store"
                style={{ minWidth: 120 }}
              />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span className="label">Location</span>
              <input
                type="text"
                value={newLocation}
                onChange={(e) => setNewLocation(e.target.value)}
                placeholder="Location"
                style={{ minWidth: 120 }}
              />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span className="label">Date</span>
              <input
                type="date"
                value={ddMmYyToIso(newDate)}
                onChange={(e) => setNewDate(isoToDdMmYy(e.target.value))}
                style={{ width: 140 }}
              />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span className="label">Format</span>
              <input
                type="text"
                value={newFormatId}
                onChange={(e) => setNewFormatId(e.target.value)}
                placeholder="EDH"
                style={{ width: 80 }}
              />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span className="label">Players (required)</span>
              <input
                type="number"
                min={1}
                value={newPlayerCount || ''}
                onChange={(e) => setNewPlayerCount(parseInt(e.target.value, 10) || 0)}
                placeholder="e.g. 8"
                style={{ width: 70 }}
                required
              />
            </label>
            <button type="button" className="btn btn-primary" onClick={handleCreate} disabled={creating}>
              {creating ? 'Creating…' : 'Create event'}
            </button>
          </div>
        </section>
      )}

      {user === 'admin' && (
        <section className="card" style={{ marginBottom: '1.5rem' }}>
          <h2 style={{ marginTop: 0 }}>Merge events</h2>
          <p className="muted" style={{ marginBottom: '1rem', fontSize: '0.9rem' }}>
            Combine two events into one. You cannot merge two events imported from MTGTop8. When merging a manual and a MTGTop8 event, MTGTop8 data is preferred; resolve any conflicts below. The removed event will be deleted (if one is manual and one MTGTop8, the manual one is removed).
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'flex-end', marginBottom: '1rem' }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span className="label">Event A</span>
              <select
                value={mergeEventIdA}
                onChange={(e) => setMergeEventIdA(e.target.value)}
                style={{ minWidth: 220 }}
              >
                <option value="">Select event…</option>
                {events.map((e) => (
                  <option key={String(e.event_id)} value={String(e.event_id)}>
                    {cellStr(e.event_name) || 'Unnamed'} ({cellStr(e.date)}) {e.origin === 'manual' ? ' [manual]' : ''}
                  </option>
                ))}
              </select>
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span className="label">Event B</span>
              <select
                value={mergeEventIdB}
                onChange={(e) => setMergeEventIdB(e.target.value)}
                style={{ minWidth: 220 }}
              >
                <option value="">Select event…</option>
                {events.map((e) => (
                  <option key={String(e.event_id)} value={String(e.event_id)}>
                    {cellStr(e.event_name) || 'Unnamed'} ({cellStr(e.date)}) {e.origin === 'manual' ? ' [manual]' : ''}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" className="btn" onClick={handleMergePreview} disabled={mergeLoading}>
              {mergeLoading ? 'Loading…' : 'Preview merge'}
            </button>
          </div>
          {mergePreview && (
            <div style={{ borderTop: '1px solid var(--border)', paddingTop: '1rem' }}>
              {!mergePreview.can_merge && mergePreview.error && (
                <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>{mergePreview.error}</p>
              )}
              {mergePreview.can_merge && (
                <>
                  <p style={{ marginBottom: '0.75rem' }}>
                    <strong>Kept event:</strong> {mergePreview.event_a.event_id === mergePreview.keep_event_id ? 'A' : 'B'} ({cellStr(mergePreview.merged_preview.event_name)}).{' '}
                    <strong>Removed event:</strong> {mergePreview.event_a.event_id === mergePreview.remove_event_id ? 'A' : 'B'} (will be deleted).
                  </p>
                  <div style={{ marginBottom: '1rem' }}>
                    <span className="label">Merged result preview</span>
                    <ul style={{ margin: '0.25rem 0 0', paddingLeft: '1.25rem' }}>
                      <li>Name: {cellStr(mergePreview.merged_preview.event_name) || '—'}</li>
                      <li>Date: {cellStr(mergePreview.merged_preview.date) || '—'}</li>
                      <li>Format: {cellStr(mergePreview.merged_preview.format_id) || '—'}</li>
                      <li>Players: {mergePreview.merged_preview.player_count ?? '—'}</li>
                      <li>Store: {cellStr(mergePreview.merged_preview.store) || '—'}</li>
                      <li>Location: {cellStr(mergePreview.merged_preview.location) || '—'}</li>
                    </ul>
                  </div>
                  {mergePreview.conflicts.length > 0 && (
                    <div style={{ marginBottom: '1rem' }}>
                      <span className="label">Event: resolve conflicts (choose which value to keep)</span>
                      <ul style={{ margin: '0.25rem 0 0', paddingLeft: 0, listStyle: 'none' }}>
                        {mergePreview.conflicts.map((c) => (
                          <li key={c.field} style={{ marginBottom: '0.5rem' }}>
                            <strong>{mergeFieldLabel[c.field] ?? c.field}:</strong>{' '}
                            <label style={{ marginLeft: '0.5rem' }}>
                              <input
                                type="radio"
                                name={`merge-${c.field}`}
                                checked={(mergeResolutions[c.field] ?? 'keep') === 'keep'}
                                onChange={() => setMergeResolutions((r) => ({ ...r, [c.field]: 'keep' }))}
                              />
                              {' '}Kept: {String(c.value_keep)}
                            </label>
                            <label style={{ marginLeft: '0.75rem' }}>
                              <input
                                type="radio"
                                name={`merge-${c.field}`}
                                checked={mergeResolutions[c.field] === 'remove'}
                                onChange={() => setMergeResolutions((r) => ({ ...r, [c.field]: 'remove' }))}
                              />
                              {' '}Removed: {String(c.value_remove)}
                            </label>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {(mergePreview.deck_pairs?.length > 0 || mergePreview.decks_remove_only?.length > 0 || mergePreview.decks_keep_only?.length > 0) && (
                    <div style={{ marginBottom: '1rem' }}>
                      <span className="label">Players / decks</span>
                      {mergePreview.deck_pairs && mergePreview.deck_pairs.length > 0 && (
                        <div style={{ marginTop: '0.5rem' }}>
                          <strong>Same player in both events (will merge into one deck):</strong>
                          <ul style={{ margin: '0.25rem 0 0', paddingLeft: '1.25rem' }}>
                            {mergePreview.deck_pairs.map((pair) => {
                              const key = pairKey(pair.deck_keep.deck_id, pair.deck_remove.deck_id)
                              const res = deckResolutions[key] ?? {}
                              return (
                                <li key={key} style={{ marginBottom: '0.75rem' }}>
                                  <span>{pair.deck_keep.player} (kept deck #{pair.deck_keep.deck_id}) ↔ (removed deck #{pair.deck_remove.deck_id})</span>
                                  {pair.conflicts.length > 0 && (
                                    <ul style={{ marginTop: '0.25rem', paddingLeft: '1rem', listStyle: 'none' }}>
                                      {pair.conflicts.map((c) => (
                                        <li key={c.field} style={{ marginBottom: '0.25rem' }}>
                                          <strong>{mergeFieldLabel[c.field] ?? c.field}:</strong>{' '}
                                          <label style={{ marginLeft: '0.35rem' }}>
                                            <input
                                              type="radio"
                                              name={`deck-${key}-${c.field}`}
                                              checked={(res[c.field] ?? 'keep') === 'keep'}
                                              onChange={() => setDeckResolutions((prev) => ({
                                                ...prev,
                                                [key]: { ...prev[key], [c.field]: 'keep' as const },
                                              }))}
                                            />
                                            {' '}Kept: {conflictVal(c.value_keep)}
                                          </label>
                                          <label style={{ marginLeft: '0.5rem' }}>
                                            <input
                                              type="radio"
                                              name={`deck-${key}-${c.field}`}
                                              checked={res[c.field] === 'remove'}
                                              onChange={() => setDeckResolutions((prev) => ({
                                                ...prev,
                                                [key]: { ...prev[key], [c.field]: 'remove' as const },
                                              }))}
                                            />
                                            {' '}Removed: {conflictVal(c.value_remove)}
                                          </label>
                                        </li>
                                      ))}
                                    </ul>
                                  )}
                                </li>
                              )
                            })}
                          </ul>
                        </div>
                      )}
                      {(mergePreview.decks_remove_only?.length > 0 || mergePreview.decks_keep_only?.length > 0) && (
                        <div style={{ marginTop: '0.75rem' }}>
                          <strong>Unpaired players (removed event):</strong> These decks will move to the kept event as-is unless you merge with a kept-event player.
                          <ul style={{ margin: '0.25rem 0 0', paddingLeft: '1.25rem' }}>
                            {(mergePreview.decks_remove_only ?? []).map((d) => (
                              <li key={d.deck_id} style={{ marginBottom: '0.35rem' }}>
                                {d.player} (deck #{d.deck_id})
                                {isManualPaired(d.deck_id) ? (
                                  <span style={{ marginLeft: '0.5rem' }}>
                                    → merging with kept deck #{getManualPairKeep(d.deck_id)}
                                    <button type="button" className="btn" style={{ marginLeft: '0.35rem', padding: '0.1rem 0.4rem', fontSize: '0.85rem' }} onClick={() => removeManualPair(d.deck_id)}>Undo</button>
                                  </span>
                                ) : (
                                  <>
                                    {' '}
                                    <select
                                      value={getManualPairKeep(d.deck_id) ?? ''}
                                      onChange={(e) => {
                                        const v = e.target.value
                                        if (v) addManualPair(Number(v), d.deck_id)
                                      }}
                                      style={{ marginLeft: '0.35rem', fontSize: '0.9rem' }}
                                    >
                                      <option value="">Merge with…</option>
                                      {(mergePreview.decks_keep_only ?? []).map((k) => (
                                        <option key={k.deck_id} value={k.deck_id}>{k.player} (deck #{k.deck_id})</option>
                                      ))}
                                      {mergePreview.deck_pairs?.map((p) => (
                                        <option key={p.deck_keep.deck_id} value={p.deck_keep.deck_id}>{p.deck_keep.player} (deck #{p.deck_keep.deck_id})</option>
                                      ))}
                                    </select>
                                  </>
                                )}
                              </li>
                            ))}
                          </ul>
                          {manualPairs.length > 0 && (
                            <p className="muted" style={{ marginTop: '0.5rem', fontSize: '0.85rem' }}>
                              For manual pairs, resolve any deck conflicts above (under “Same player”) after adding the pair — use the same conflict resolution for the chosen kept deck.
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={handleMergeConfirm}
                    disabled={mergeSubmitting}
                  >
                    {mergeSubmitting ? 'Merging…' : 'Confirm merge'}
                  </button>
                </>
              )}
            </div>
          )}
        </section>
      )}

      {loading ? (
        <p>Loading events…</p>
      ) : error ? (
        <div className="chart-container" style={{ textAlign: 'center', padding: '2rem' }}>
          <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>{error}</p>
          <button type="button" className="btn" onClick={() => refetch()}>Try again</button>
        </div>
      ) : events.length === 0 ? (
        <div className="chart-container" style={{ textAlign: 'center', padding: '3rem 2rem' }}>
          <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>No events yet.</p>
          {user === 'admin' && (
            <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
              Create an event above or scrape data from the Scrape page.
            </p>
          )}
        </div>
      ) : (
        <>
          <div className="events-filters toolbar toolbar--wrap-on-mobile" style={{ marginBottom: '1rem', gap: '1rem', alignItems: 'flex-end' }}>
            <label className="events-filters-item" style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span className="label">Filter by name</span>
              <input
                type="text"
                value={filterName}
                onChange={(e) => setFilterName(e.target.value)}
                placeholder="Event name contains…"
                style={{ minWidth: 180 }}
              />
            </label>
            <label className="events-filters-item" style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span className="label">Filter by date</span>
              <input
                type="date"
                value={filterDateIso}
                onChange={(e) => setFilterDateIso(e.target.value)}
                style={{ width: 140 }}
              />
            </label>
            <label className="events-filters-item" style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span className="label">Filter by format</span>
              <select
                value={filterFormat}
                onChange={(e) => setFilterFormat(e.target.value)}
                style={{ minWidth: 100 }}
              >
                <option value="">All formats</option>
                {formatOptions.map((f) => (
                  <option key={f} value={f}>{f}</option>
                ))}
              </select>
            </label>
            {user === 'admin' && (
              <label className="events-filters-item" style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={filterWithDiscrepanciesOnly}
                  onChange={(e) => setFilterWithDiscrepanciesOnly(e.target.checked)}
                />
                <span className="label">With discrepancies only</span>
              </label>
            )}
            {hasFilters && (
              <button type="button" className="btn" onClick={clearFilters}>
                Clear filters
              </button>
            )}
          </div>
          {hasFilters && (
            <p className="muted" style={{ marginBottom: '0.75rem' }}>
              Showing {filteredAndSorted.length} of {events.length} events
            </p>
          )}
          <div className="table-wrap-outer">
            <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  {user === 'admin' && (
                    <th scope="col" style={{ width: 28, textAlign: 'center' }} title="Has matchup discrepancies">
                      ⚠
                    </th>
                  )}
                  <th
                    scope="col"
                    className="sortable"
                    style={{ cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('event_name')}
                    title="Sort by event name"
                    aria-sort={sortBy === 'event_name' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : undefined}
                  >
                    Event {sortBy === 'event_name' && (sortOrder === 'asc' ? '↑' : '↓')}
                  </th>
                  <th
                    scope="col"
                    className="sortable"
                    style={{ cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('date')}
                    title="Sort by date"
                    aria-sort={sortBy === 'date' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : undefined}
                  >
                    Date {sortBy === 'date' && (sortOrder === 'asc' ? '↑' : '↓')}
                  </th>
                  <th
                    scope="col"
                    className="sortable"
                    style={{ cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('format_id')}
                    title="Sort by format"
                    aria-sort={sortBy === 'format_id' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : undefined}
                  >
                    Format {sortBy === 'format_id' && (sortOrder === 'asc' ? '↑' : '↓')}
                  </th>
                  <th
                    scope="col"
                    className="sortable"
                    style={{ cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('player_count')}
                    title="Sort by players"
                    aria-sort={sortBy === 'player_count' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : undefined}
                  >
                    Players {sortBy === 'player_count' && (sortOrder === 'asc' ? '↑' : '↓')}
                  </th>
                  <th
                    scope="col"
                    className="sortable"
                    style={{ cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('store')}
                    title="Sort by store"
                    aria-sort={sortBy === 'store' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : undefined}
                  >
                    Store {sortBy === 'store' && (sortOrder === 'asc' ? '↑' : '↓')}
                  </th>
                  <th
                    scope="col"
                    className="sortable"
                    style={{ cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('location')}
                    title="Sort by location"
                    aria-sort={sortBy === 'location' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : undefined}
                  >
                    Location {sortBy === 'location' && (sortOrder === 'asc' ? '↑' : '↓')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {filteredAndSorted.map((e) => (
                <tr key={String(e.event_id)}>
                  {user === 'admin' && (
                    <td style={{ textAlign: 'center' }} title={eventIdsWithDiscrepancies.has(String(e.event_id)) ? 'Has matchup discrepancies' : ''}>
                      {eventIdsWithDiscrepancies.has(String(e.event_id)) ? '⚠' : '—'}
                    </td>
                  )}
                  <td>
                    <Link to={`/events/${encodeURIComponent(String(e.event_id))}`} style={{ color: 'var(--accent)', fontWeight: 500 }}>
                      {(typeof e.event_name === 'string' && e.event_name.trim()) ? e.event_name : 'Unnamed'}
                    </Link>
                  </td>
                  <td>{cellStr(e.date)}</td>
                  <td>{cellStr(e.format_id) || '—'}</td>
                  <td>{typeof e.player_count === 'number' ? e.player_count : '—'}</td>
                  <td>{cellStr(e.store) || '—'}</td>
                  <td>{cellStr(e.location) || '—'}</td>
                </tr>
              ))}
              </tbody>
            </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
