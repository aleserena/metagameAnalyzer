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
} from '../api'

const RANK_KEYS = ['1', '2', '3-4', '5-8', '9-16', '17-32'] as const
const DEFAULT_RANK_WEIGHTS: Record<string, number> = {
  '1': 8,
  '2': 6,
  '3-4': 4,
  '5-8': 2,
  '9-16': 1,
  '17-32': 0.5,
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

  useEffect(() => {
    getPlayerAliases()
      .then((r) => setAliases(r.aliases))
      .catch((e) => toast.error(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoadingAliases(false))
  }, [])

  useEffect(() => {
    getIgnoreLandsCards()
      .then((r) => setIgnoreLandsCards(r.cards))
      .catch((e) => toast.error(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoadingCards(false))
  }, [])

  useEffect(() => {
    getRankWeights()
      .then((r) => setRankWeights({ ...DEFAULT_RANK_WEIGHTS, ...r.weights }))
      .catch((e) => toast.error(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoadingRankWeights(false))
  }, [])

  const handleAddAlias = () => {
    if (!newAlias.trim() || !newCanonical.trim()) return
    addPlayerAlias(newAlias.trim(), newCanonical.trim())
      .then((r) => {
        setAliases(r.aliases)
        setNewAlias('')
        setNewCanonical('')
        toast.success('Alias added')
      })
      .catch((e) => toast.error(e instanceof Error ? e.message : String(e)))
  }

  const handleRemoveAlias = (alias: string) => {
    removePlayerAlias(alias)
      .then((r) => {
        setAliases(r.aliases)
        toast.success('Alias removed')
      })
      .catch((e) => toast.error(e instanceof Error ? e.message : String(e)))
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
      .catch((e) => toast.error(e instanceof Error ? e.message : String(e)))
  }

  const handleRemoveIgnoreCard = (card: string) => {
    const updated = ignoreLandsCards.filter((c) => c !== card)
    putIgnoreLandsCards(updated)
      .then((r) => {
        setIgnoreLandsCards(r.cards)
        toast.success('Card removed from ignore list')
      })
      .catch((e) => toast.error(e instanceof Error ? e.message : String(e)))
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
      .catch((e) => toast.error(e instanceof Error ? e.message : String(e)))
      .finally(() => setSavingRankWeights(false))
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
