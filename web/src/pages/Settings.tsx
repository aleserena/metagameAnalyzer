import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import {
  getPlayerAliases,
  addPlayerAlias,
  removePlayerAlias,
  getIgnoreLandsCards,
  putIgnoreLandsCards,
  getRankWeights,
  putRankWeights,
  getMatchupsMinMatchesSetting,
  putMatchupsMinMatchesSetting,
  getMatchupsPlayersMinMatchesSetting,
  putMatchupsPlayersMinMatchesSetting,
  clearScryfallCache,
  clearDecks,
  getUploadLinks,
  clearUploadLinks,
} from '../api'
import type { UploadLinkRow } from '../api'
import { reportError } from '../utils'

const RANK_KEYS = ['1', '2', '3-4', '5-8', '9-16', '17-32', '33-64', '65-128'] as const
const DEFAULT_RANK_WEIGHTS: Record<string, number> = {
  '1': 8,
  '2': 6,
  '3-4': 4,
  '5-8': 2,
  '9-16': 1,
  '17-32': 0.5,
  '33-64': 0.25,
  '65-128': 0.125,
}

export default function Settings() {
  const [aliases, setAliases] = useState<Record<string, string>>({})
  const [newAlias, setNewAlias] = useState('')
  const [newCanonical, setNewCanonical] = useState('')
  const [ignoreLandsCards, setIgnoreLandsCards] = useState<string[]>([])
  const [newIgnoreCard, setNewIgnoreCard] = useState('')
  const [loadingAliases, setLoadingAliases] = useState(true)
  const [loadingCards, setLoadingCards] = useState(true)
  const [rankWeights, setRankWeights] = useState<Record<string, number>>(DEFAULT_RANK_WEIGHTS)
  const [loadingRankWeights, setLoadingRankWeights] = useState(true)
  const [savingRankWeights, setSavingRankWeights] = useState(false)
  const [clearingCache, setClearingCache] = useState(false)
  const [clearingDecks, setClearingDecks] = useState(false)
  const [uploadLinks, setUploadLinks] = useState<UploadLinkRow[]>([])
  const [loadingUploadLinks, setLoadingUploadLinks] = useState(true)
  const [clearingLinks, setClearingLinks] = useState<'used' | 'all' | null>(null)
  const [matchupsMinMatches, setMatchupsMinMatches] = useState(0)
  const [loadingMatchupsMin, setLoadingMatchupsMin] = useState(true)
  const [savingMatchupsMin, setSavingMatchupsMin] = useState(false)
  const [matchupsPlayersMinMatches, setMatchupsPlayersMinMatches] = useState(0)
  const [loadingMatchupsPlayersMin, setLoadingMatchupsPlayersMin] = useState(true)
  const [savingMatchupsPlayersMin, setSavingMatchupsPlayersMin] = useState(false)

  useEffect(() => {
    getPlayerAliases()
      .then((r) => setAliases(r.aliases))
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setLoadingAliases(false))
  }, [])

  useEffect(() => {
    getIgnoreLandsCards()
      .then((r) => setIgnoreLandsCards(r.cards))
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setLoadingCards(false))
  }, [])

  useEffect(() => {
    getRankWeights()
      .then((r) => setRankWeights({ ...DEFAULT_RANK_WEIGHTS, ...r.weights }))
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setLoadingRankWeights(false))
  }, [])

  const loadUploadLinks = () => {
    setLoadingUploadLinks(true)
    getUploadLinks()
      .then((r) => setUploadLinks(r.links))
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setLoadingUploadLinks(false))
  }

  useEffect(() => {
    loadUploadLinks()
  }, [])

  useEffect(() => {
    getMatchupsMinMatchesSetting()
      .then((r) => setMatchupsMinMatches(r.value))
      .catch(() => setMatchupsMinMatches(0))
      .finally(() => setLoadingMatchupsMin(false))
  }, [])

  useEffect(() => {
    getMatchupsPlayersMinMatchesSetting()
      .then((r) => setMatchupsPlayersMinMatches(r.value))
      .catch(() => setMatchupsPlayersMinMatches(0))
      .finally(() => setLoadingMatchupsPlayersMin(false))
  }, [])

  const handleSaveMatchupsMinMatches = () => {
    setSavingMatchupsMin(true)
    putMatchupsMinMatchesSetting(matchupsMinMatches)
      .then((r) => {
        setMatchupsMinMatches(r.value)
        toast.success('Minimum matches saved')
      })
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setSavingMatchupsMin(false))
  }

  const handleSaveMatchupsPlayersMinMatches = () => {
    setSavingMatchupsPlayersMin(true)
    putMatchupsPlayersMinMatchesSetting(matchupsPlayersMinMatches)
      .then((r) => {
        setMatchupsPlayersMinMatches(r.value)
        toast.success('Player matchups minimum matches saved')
      })
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setSavingMatchupsPlayersMin(false))
  }

  const handleAddAlias = () => {
    if (!newAlias.trim() || !newCanonical.trim()) return
    addPlayerAlias(newAlias.trim(), newCanonical.trim())
      .then((r) => {
        setAliases(r.aliases)
        setNewAlias('')
        setNewCanonical('')
        toast.success('Alias added')
      })
      .catch((e) => toast.error(reportError(e)))
  }

  const handleRemoveAlias = (alias: string) => {
    removePlayerAlias(alias)
      .then((r) => {
        setAliases(r.aliases)
        toast.success('Alias removed')
      })
      .catch((e) => toast.error(reportError(e)))
  }

  const handleAddIgnoreCard = () => {
    const card = newIgnoreCard.trim()
    if (!card) return
    if (ignoreLandsCards.includes(card)) {
      toast.error('Card already in list')
      return
    }
    const updated = [...ignoreLandsCards, card].sort()
    putIgnoreLandsCards(updated)
      .then((r) => {
        setIgnoreLandsCards(r.cards)
        setNewIgnoreCard('')
        toast.success('Card added to ignore list')
      })
      .catch((e) => toast.error(reportError(e)))
  }

  const handleRemoveIgnoreCard = (card: string) => {
    const updated = ignoreLandsCards.filter((c) => c !== card)
    putIgnoreLandsCards(updated)
      .then((r) => {
        setIgnoreLandsCards(r.cards)
        toast.success('Card removed from ignore list')
      })
      .catch((e) => toast.error(reportError(e)))
  }

  const handleSaveRankWeights = () => {
    setSavingRankWeights(true)
    const toSave: Record<string, number> = { ...DEFAULT_RANK_WEIGHTS }
    RANK_KEYS.forEach((k) => {
      const v = rankWeights[k]
      if (typeof v === 'number' && !Number.isNaN(v)) toSave[k] = v
    })
    putRankWeights(toSave)
      .then((r) => {
        setRankWeights({ ...DEFAULT_RANK_WEIGHTS, ...r.weights })
        toast.success('Points per position saved')
      })
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setSavingRankWeights(false))
  }

  const handleClearCache = () => {
    if (!window.confirm('Clear the Scryfall card lookup cache? Card images and metadata will be re-fetched on next use.')) return
    setClearingCache(true)
    clearScryfallCache()
      .then(() => toast.success('Scryfall cache cleared'))
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setClearingCache(false))
  }

  const handleClearDecks = () => {
    if (!window.confirm('Clear all decks? This removes all loaded/scraped data and overwrites decks.json. This cannot be undone.')) return
    setClearingDecks(true)
    clearDecks()
      .then(() => toast.success('Decks cleared'))
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setClearingDecks(false))
  }

  const handleClearUploadLinks = (usedOnly: boolean) => {
    const msg = usedOnly
      ? 'Clear all used one-time links? Unused links will remain.'
      : 'Clear all one-time upload links? This cannot be undone.'
    if (!window.confirm(msg)) return
    setClearingLinks(usedOnly ? 'used' : 'all')
    clearUploadLinks(usedOnly)
      .then((r) => {
        toast.success(r.message)
        loadUploadLinks()
      })
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setClearingLinks(null))
  }

  return (
    <div>
      <h1 className="page-title">Settings</h1>

      <div className="chart-container" style={{ maxWidth: 600, marginBottom: '2rem' }}>
        <h2 style={{ margin: '0 0 1rem', fontSize: '1.25rem' }}>Player aliases</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '1rem' }}>
          Map alternate names to a canonical name. E.g. &quot;Pablo Tomas Pesci&quot; → &quot;Tomas Pesci&quot; merges stats across the app.
        </p>
        {loadingAliases ? (
          <p style={{ color: 'var(--text-muted)' }}>Loading...</p>
        ) : (
          <>
            {Object.keys(aliases).length > 0 && (
              <div style={{ marginBottom: '1rem' }}>
                <div style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                  Current aliases
                </div>
                {Object.entries(aliases).map(([alias, canonical]) => (
                  <div
                    key={alias}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      padding: '0.35rem 0',
                      fontSize: '0.9rem',
                    }}
                  >
                    <span>{alias}</span>
                    <span style={{ color: 'var(--text-muted)' }}>→</span>
                    <Link to={`/players/${encodeURIComponent(canonical)}`} style={{ color: 'var(--accent)' }}>
                      {canonical}
                    </Link>
                    <button
                      type="button"
                      onClick={() => handleRemoveAlias(alias)}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: 'var(--text-muted)',
                        cursor: 'pointer',
                        fontSize: '0.8rem',
                      }}
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
              <input
                type="text"
                placeholder="Alias (e.g. Pablo Tomas Pesci)"
                value={newAlias}
                onChange={(e) => setNewAlias(e.target.value)}
                style={{ padding: '0.35rem 0.5rem', minWidth: 180 }}
              />
              <span style={{ color: 'var(--text-muted)' }}>→</span>
              <input
                type="text"
                placeholder="Canonical (e.g. Tomas Pesci)"
                value={newCanonical}
                onChange={(e) => setNewCanonical(e.target.value)}
                style={{ padding: '0.35rem 0.5rem', minWidth: 180 }}
              />
              <button type="button" className="btn" style={{ padding: '0.35rem 0.75rem' }} onClick={handleAddAlias}>
                Add merge
              </button>
            </div>
          </>
        )}
      </div>

      <div className="chart-container" style={{ maxWidth: 600, marginBottom: '2rem' }}>
        <h2 style={{ margin: '0 0 1rem', fontSize: '1.25rem' }}>Points per position</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '1rem' }}>
          Points awarded for each placement in the player leaderboard and for placement-weighted metagame stats.
        </p>
        {loadingRankWeights ? (
          <p style={{ color: 'var(--text-muted)' }}>Loading...</p>
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center' }}>
            {RANK_KEYS.map((rank) => (
              <label key={rank} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem' }}>
                <span style={{ minWidth: 48 }}>{rank}:</span>
                <input
                  type="number"
                  min={0}
                  step={0.5}
                  value={rankWeights[rank] ?? ''}
                  onChange={(e) => {
                    const v = e.target.value
                    const n = v === '' ? 0 : parseFloat(v)
                    if (!Number.isNaN(n)) setRankWeights((w) => ({ ...w, [rank]: n }))
                  }}
                  style={{ width: 72, padding: '0.35rem 0.5rem' }}
                />
                <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>pts</span>
              </label>
            ))}
            <button
              type="button"
              className="btn"
              style={{ padding: '0.35rem 0.75rem' }}
              onClick={handleSaveRankWeights}
              disabled={savingRankWeights}
            >
              {savingRankWeights ? 'Saving...' : 'Save'}
            </button>
          </div>
        )}
      </div>

      <div className="chart-container" style={{ maxWidth: 600, marginBottom: '2rem' }}>
        <h2 style={{ margin: '0 0 1rem', fontSize: '1.25rem' }}>Matchups: minimum matches</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '1rem' }}>
          On the Matchups page, only archetype pairs with at least this many reported matches are shown.
        </p>
        {loadingMatchupsMin ? (
          <p style={{ color: 'var(--text-muted)' }}>Loading...</p>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            <input
              type="number"
              min={0}
              value={matchupsMinMatches}
              onChange={(e) => setMatchupsMinMatches(Math.max(0, parseInt(e.target.value, 10) || 0))}
              style={{ width: 72, padding: '0.35rem 0.5rem' }}
            />
            <button
              type="button"
              className="btn"
              style={{ padding: '0.35rem 0.75rem' }}
              onClick={handleSaveMatchupsMinMatches}
              disabled={savingMatchupsMin}
            >
              {savingMatchupsMin ? 'Saving...' : 'Save'}
            </button>
          </div>
        )}
      </div>

      <div className="chart-container" style={{ maxWidth: 600, marginBottom: '2rem' }}>
        <h2 style={{ margin: '0 0 1rem', fontSize: '1.25rem' }}>Matchups (players): minimum matches</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '1rem' }}>
          On the Matchups page (Players view), only player pairs with at least this many reported matches are shown.
        </p>
        {loadingMatchupsPlayersMin ? (
          <p style={{ color: 'var(--text-muted)' }}>Loading...</p>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            <input
              type="number"
              min={0}
              value={matchupsPlayersMinMatches}
              onChange={(e) => setMatchupsPlayersMinMatches(Math.max(0, parseInt(e.target.value, 10) || 0))}
              style={{ width: 72, padding: '0.35rem 0.5rem' }}
            />
            <button
              type="button"
              className="btn"
              style={{ padding: '0.35rem 0.75rem' }}
              onClick={handleSaveMatchupsPlayersMinMatches}
              disabled={savingMatchupsPlayersMin}
            >
              {savingMatchupsPlayersMin ? 'Saving...' : 'Save'}
            </button>
          </div>
        )}
      </div>

      <div className="chart-container" style={{ maxWidth: 600, marginBottom: '2rem' }}>
        <h2 style={{ margin: '0 0 1rem', fontSize: '1.25rem' }}>Data &amp; cache</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '1rem' }}>
          Clear the Scryfall cache to force re-fetching card images and metadata. Clear decks to remove all loaded/scraped data and reset decks.json.
        </p>
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          <button
            type="button"
            className="btn"
            style={{ padding: '0.35rem 0.75rem' }}
            onClick={handleClearCache}
            disabled={clearingCache}
          >
            {clearingCache ? 'Clearing...' : 'Clear Scryfall cache'}
          </button>
          <button
            type="button"
            className="btn"
            style={{ padding: '0.35rem 0.75rem' }}
            onClick={handleClearDecks}
            disabled={clearingDecks}
          >
            {clearingDecks ? 'Clearing...' : 'Clear decks.json'}
          </button>
        </div>
      </div>

      <div className="chart-container" style={{ maxWidth: 800, marginBottom: '2rem' }}>
        <h2 style={{ margin: '0 0 1rem', fontSize: '1.25rem' }}>One-time upload links</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '1rem' }}>
          View and clear one-time links for deck upload or update. Used links cannot be used again; clearing them only removes them from this list.
        </p>
        {loadingUploadLinks ? (
          <p style={{ color: 'var(--text-muted)' }}>Loading...</p>
        ) : (
          <>
            <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
              <button
                type="button"
                className="btn"
                style={{ padding: '0.35rem 0.75rem' }}
                onClick={() => handleClearUploadLinks(true)}
                disabled={clearingLinks !== null || uploadLinks.filter((l) => l.used_at).length === 0}
              >
                {clearingLinks === 'used' ? 'Clearing...' : 'Clear used only'}
              </button>
              <button
                type="button"
                className="btn"
                style={{ padding: '0.35rem 0.75rem' }}
                onClick={() => handleClearUploadLinks(false)}
                disabled={clearingLinks !== null || uploadLinks.length === 0}
              >
                {clearingLinks === 'all' ? 'Clearing...' : 'Clear all'}
              </button>
              <button
                type="button"
                className="btn"
                style={{ padding: '0.35rem 0.75rem' }}
                onClick={loadUploadLinks}
                disabled={loadingUploadLinks}
              >
                Refresh
              </button>
            </div>
            {uploadLinks.length === 0 ? (
              <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>No one-time links.</p>
            ) : (
              <div className="table-wrap" style={{ maxHeight: 360, overflow: 'auto' }}>
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Event</th>
                      <th scope="col">Type</th>
                      <th scope="col">Created</th>
                      <th scope="col">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {uploadLinks.map((l) => (
                      <tr key={l.token}>
                        <td>
                          <Link to={`/events/${l.event_id}`} style={{ color: 'var(--accent)' }}>
                            {l.event_id}
                          </Link>
                        </td>
                        <td>{l.deck_id != null ? `Update deck ${l.deck_id}` : 'Create'}</td>
                        <td style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                          {l.created_at ? new Date(l.created_at).toLocaleString() : '—'}
                        </td>
                        <td>
                          {l.used_at ? (
                            <span style={{ color: 'var(--text-muted)' }}>Used</span>
                          ) : l.expires_at && new Date(l.expires_at) < new Date() ? (
                            <span style={{ color: 'var(--text-muted)' }}>Expired</span>
                          ) : (
                            <span style={{ color: 'var(--success, green)' }}>Active</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>

      <div className="chart-container" style={{ maxWidth: 600 }}>
        <h2 style={{ margin: '0 0 1rem', fontSize: '1.25rem' }}>Cards ignored by &quot;Ignore lands&quot;</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '1rem' }}>
          These cards are excluded from Metagame (top cards, synergy) when the &quot;Ignore lands&quot; checkbox is checked on Dashboard and Metagame pages.
        </p>
        {loadingCards ? (
          <p style={{ color: 'var(--text-muted)' }}>Loading...</p>
        ) : (
          <>
            <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
              <input
                type="text"
                placeholder="Card name (e.g. Command Tower)"
                value={newIgnoreCard}
                onChange={(e) => setNewIgnoreCard(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAddIgnoreCard()}
                style={{ padding: '0.35rem 0.5rem', flex: 1, maxWidth: 280 }}
              />
              <button type="button" className="btn" style={{ padding: '0.35rem 0.75rem' }} onClick={handleAddIgnoreCard}>
                Add card
              </button>
            </div>
            <div style={{ maxHeight: 320, overflow: 'auto', border: '1px solid var(--border)', borderRadius: 8, padding: '0.5rem' }}>
              {ignoreLandsCards.length === 0 ? (
                <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>No cards in list (default set is used). Add cards to extend the list.</p>
              ) : (
                ignoreLandsCards.map((card) => (
                  <div
                    key={card}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '0.25rem 0',
                      fontSize: '0.9rem',
                    }}
                  >
                    <span>{card}</span>
                    <button
                      type="button"
                      onClick={() => handleRemoveIgnoreCard(card)}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: 'var(--text-muted)',
                        cursor: 'pointer',
                        fontSize: '0.8rem',
                      }}
                    >
                      Remove
                    </button>
                  </div>
                ))
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
