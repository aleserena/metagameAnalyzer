import { useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import Modal from '../Modal'
import { applyHadoukenImport, previewHadoukenImport } from '../../api'
import type { HadoukenMatchKind, HadoukenPreview } from '../../types'
import { reportError } from '../../utils'

const MATCH_LABELS: Record<HadoukenMatchKind, string> = {
  player: 'Same player',
  reordered: 'Name reordered',
  partial: 'Partial name — check',
  none: 'New deck',
}

const NEW_DECK = 'new'

interface Props {
  eventId: string
  onClose: () => void
  /** Called after a successful import so the page can reload decks. */
  onImported: () => void
}

/**
 * Complete an event (usually scraped from MTGTop8) with all players and round results from a
 * Hadouken league page: paste URL -> review player matching -> import.
 */
export default function HadoukenImportModal({ eventId, onClose, onImported }: Props) {
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [preview, setPreview] = useState<HadoukenPreview | null>(null)
  // Hadouken name -> deck_id as string, or NEW_DECK
  const [mapping, setMapping] = useState<Record<string, string>>({})
  // Hadouken name -> editable place / tournament points (as typed)
  const [standings, setStandings] = useState<Record<string, { rank: string; points: string }>>({})

  const loadPreview = () => {
    if (!url.trim()) return
    setLoading(true)
    previewHadoukenImport(eventId, url.trim())
      .then((res) => {
        setPreview(res)
        setMapping(Object.fromEntries(res.players.map((p) => [p.name, p.deck_id != null ? String(p.deck_id) : NEW_DECK])))
        setStandings(Object.fromEntries(res.players.map((p) => [p.name, { rank: String(p.rank), points: String(p.points) }])))
      })
      .catch((e) => {
        setPreview(null)
        toast.error(reportError(e))
      })
      .finally(() => setLoading(false))
  }

  const updateStanding = (name: string, field: 'rank' | 'points', value: string) =>
    setStandings((s) => ({ ...s, [name]: { ...s[name], [field]: value } }))

  // Parsed standings; null when a value is not a valid number (place >= 1, points >= 0)
  const parsedStandings = useMemo(() => {
    const out: Record<string, { rank: number; points: number } | null> = {}
    for (const [name, s] of Object.entries(standings)) {
      const rank = /^\d+$/.test(s.rank.trim()) ? Number(s.rank) : NaN
      const points = /^\d+$/.test(s.points.trim()) ? Number(s.points) : NaN
      out[name] = rank >= 1 && points >= 0 ? { rank, points } : null
    }
    return out
  }, [standings])

  const invalidStandings = Object.keys(parsedStandings).filter((n) => parsedStandings[n] == null)
  const duplicateRanks = useMemo(() => {
    const counts = new Map<number, number>()
    for (const s of Object.values(parsedStandings)) if (s) counts.set(s.rank, (counts.get(s.rank) ?? 0) + 1)
    return new Set([...counts].filter(([, c]) => c > 1).map(([r]) => r))
  }, [parsedStandings])

  // The tournament winner is whoever has the most tournament points (ties: any of them, tiebreakers may differ).
  const leaders = useMemo(() => {
    const valid = Object.entries(parsedStandings).filter(([, s]) => s != null) as Array<[string, { rank: number; points: number }]>
    if (!valid.length) return []
    const max = Math.max(...valid.map(([, s]) => s.points))
    return valid.filter(([, s]) => s.points === max).map(([n]) => n)
  }, [parsedStandings])
  const firstPlace = Object.keys(parsedStandings).find((n) => parsedStandings[n]?.rank === 1)
  let standingsWarning: string | null = null
  if (preview && !invalidStandings.length) {
    if (!firstPlace) standingsWarning = 'No player is in 1st place.'
    else if (!leaders.includes(firstPlace)) {
      standingsWarning = `1st place ${firstPlace} has ${parsedStandings[firstPlace]?.points} pts, but ${leaders.join(' / ')} has more.`
    }
  }

  const duplicateDeckIds = useMemo(() => {
    const seen = new Set<string>()
    const dupes = new Set<string>()
    for (const v of Object.values(mapping)) {
      if (v === NEW_DECK) continue
      if (seen.has(v)) dupes.add(v)
      seen.add(v)
    }
    return dupes
  }, [mapping])

  const newDeckCount = Object.values(mapping).filter((v) => v === NEW_DECK).length
  const assignedDeckIds = new Set(Object.values(mapping).filter((v) => v !== NEW_DECK))
  const unassignedDecks = preview ? preview.decks.filter((d) => !assignedDeckIds.has(String(d.deck_id))) : []

  // The MTGTop8 winner (deck ranked 1) must be a Hadouken player with the most tournament points.
  const winnerDeck = preview?.decks.find((d) => d.rank.trim() === '1')
  const winnerName = winnerDeck ? Object.keys(mapping).find((n) => mapping[n] === String(winnerDeck.deck_id)) : undefined
  let winnerWarning: string | null = null
  if (preview && winnerDeck && leaders.length) {
    const leaderNames = leaders.join(' / ')
    if (!winnerName) {
      winnerWarning = `MTGTop8 winner ${winnerDeck.player || 'Unnamed'} is not matched to any Hadouken player (most points: ${leaderNames}).`
    } else if (!leaders.includes(winnerName)) {
      winnerWarning = `MTGTop8 winner ${winnerDeck.player || 'Unnamed'} is matched to ${winnerName}, but the most tournament points are ${leaderNames}'s.`
    }
  }

  const standingsBlocked = invalidStandings.length > 0 || duplicateRanks.size > 0

  const handleApply = () => {
    if (!preview || duplicateDeckIds.size || standingsBlocked) return
    const playerMap = Object.fromEntries(
      Object.entries(mapping).map(([name, v]) => [name, v === NEW_DECK ? null : Number(v)])
    )
    // Send only the standings that were edited
    const standingsEdits = Object.fromEntries(
      preview.players
        .filter((p) => parsedStandings[p.name] && (parsedStandings[p.name]!.rank !== p.rank || parsedStandings[p.name]!.points !== p.points))
        .map((p) => [p.name, parsedStandings[p.name]!])
    )
    setApplying(true)
    applyHadoukenImport(eventId, preview.hadouken.url, playerMap, standingsEdits)
      .then((res) => {
        toast.success(
          `Imported ${res.matches_imported} matches. ${res.decks_created} new deck(s), ${res.decks_matched} matched.`
        )
        onImported()
        onClose()
      })
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setApplying(false))
  }

  const busy = loading || applying
  return (
    <Modal title="Import from Hadouken" onClose={() => !busy && onClose()} closeOnOverlayClick={!busy} size={760}>
      <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginTop: 0 }}>
        Adds the players missing from this event (as decks without a list) and every round result from a
        Hadouken league tournament page. Existing decks and lists are kept.
      </p>
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
        <input
          type="url"
          placeholder="https://hadoleague.vercel.app/torneos/…"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && loadPreview()}
          style={{ flex: 1, minWidth: 0 }}
          disabled={busy}
          aria-label="Hadouken tournament URL"
        />
        <button type="button" className="btn" onClick={loadPreview} disabled={busy || !url.trim()}>
          {loading ? 'Loading…' : 'Preview'}
        </button>
      </div>

      {preview && (
        <>
          <p style={{ margin: '0 0 0.75rem' }}>
            <strong>{preview.hadouken.name}</strong> — {preview.hadouken.date} · {preview.hadouken.player_count} players ·{' '}
            {preview.pairings.length} matches
          </p>
          {preview.warnings.map((w) => (
            <p key={w} style={{ margin: '0 0 0.5rem', color: 'var(--danger, #c00)', fontSize: '0.9rem' }}>⚠ {w}</p>
          ))}
          {standingsWarning && (
            <p style={{ margin: '0 0 0.5rem', color: 'var(--danger, #c00)', fontSize: '0.9rem' }}>⚠ {standingsWarning}</p>
          )}
          {winnerWarning && (
            <p style={{ margin: '0 0 0.5rem', color: 'var(--danger, #c00)', fontSize: '0.9rem' }}>⚠ {winnerWarning}</p>
          )}
          {standingsBlocked && (
            <p style={{ margin: '0 0 0.5rem', color: 'var(--danger, #c00)', fontSize: '0.9rem' }}>
              ✖ Fix the standings before importing:{' '}
              {invalidStandings.length > 0 && `invalid place or points for ${invalidStandings.join(', ')}. `}
              {duplicateRanks.size > 0 && `place(s) ${[...duplicateRanks].sort((a, b) => a - b).join(', ')} used more than once.`}
            </p>
          )}
          {preview.conflicts.length > 0 && (
            <p style={{ margin: '0 0 0.5rem', color: 'var(--danger, #c00)', fontSize: '0.9rem' }}>
              ⚠ {preview.conflicts.length} stored result(s) differ from Hadouken and will be replaced:{' '}
              {preview.conflicts.map((c) => `R${c.round} ${c.player1} vs ${c.player2} (${c.existing} → ${c.hadouken})`).join('; ')}
            </p>
          )}

          <div className="table-wrap" style={{ maxHeight: '50vh', overflow: 'auto', marginBottom: '0.75rem' }}>
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Hadouken player</th>
                  <th>Pts</th>
                  <th>W-L-D</th>
                  <th>Deck in this event</th>
                  <th>Match</th>
                </tr>
              </thead>
              <tbody>
                {preview.players.map((p) => {
                  const value = mapping[p.name] ?? NEW_DECK
                  const original = p.deck_id != null ? String(p.deck_id) : NEW_DECK
                  const kind: HadoukenMatchKind = value === original ? p.match : value === NEW_DECK ? 'none' : 'player'
                  const isDupe = duplicateDeckIds.has(value)
                  const st = standings[p.name] ?? { rank: '', points: '' }
                  const parsed = parsedStandings[p.name]
                  const rankBad = !parsed || duplicateRanks.has(parsed.rank)
                  const badStyle = { borderColor: 'var(--danger, #c00)' }
                  return (
                    <tr key={p.name}>
                      <td>
                        <input
                          type="number"
                          min={1}
                          value={st.rank}
                          onChange={(e) => updateStanding(p.name, 'rank', e.target.value)}
                          disabled={busy}
                          aria-label={`Place of ${p.name}`}
                          style={{ width: 56, ...(rankBad ? badStyle : {}) }}
                        />
                        {p.hadouken_rank !== p.rank && (
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }} title="Place on the Hadouken page">
                            page #{p.hadouken_rank}
                          </div>
                        )}
                      </td>
                      <td>{p.name}</td>
                      <td>
                        <input
                          type="number"
                          min={0}
                          value={st.points}
                          onChange={(e) => updateStanding(p.name, 'points', e.target.value)}
                          disabled={busy}
                          aria-label={`Tournament points of ${p.name}`}
                          style={{ width: 56, ...(!parsed ? badStyle : {}) }}
                        />
                      </td>
                      <td>{p.wins}-{p.losses}-{p.draws}</td>
                      <td>
                        <select
                          value={value}
                          onChange={(e) => setMapping((m) => ({ ...m, [p.name]: e.target.value }))}
                          disabled={busy}
                          aria-label={`Deck for ${p.name}`}
                          style={isDupe ? { borderColor: 'var(--danger, #c00)' } : undefined}
                        >
                          <option value={NEW_DECK}>➕ New deck</option>
                          {preview.decks.map((d) => (
                            <option key={d.deck_id} value={String(d.deck_id)}>
                              {d.player || 'Unnamed'}{d.rank ? ` (#${d.rank})` : ''}{d.archetype ? ` — ${d.archetype}` : ''}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td
                        style={{
                          fontSize: '0.85rem',
                          color: isDupe || kind === 'partial' ? 'var(--danger, #c00)' : 'var(--text-muted)',
                        }}
                      >
                        {isDupe ? 'Deck used twice' : value !== original ? 'Manual' : MATCH_LABELS[kind]}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {unassignedDecks.length > 0 && (
            <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', margin: '0 0 0.75rem' }}>
              Decks not matched to any Hadouken player (left unchanged):{' '}
              {unassignedDecks.map((d) => d.player || 'Unnamed').join(', ')}
            </p>
          )}

          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleApply}
              disabled={busy || duplicateDeckIds.size > 0 || standingsBlocked}
            >
              {applying ? 'Importing…' : `Import ${preview.pairings.length} matches${newDeckCount ? ` + ${newDeckCount} new deck(s)` : ''}`}
            </button>
            <button type="button" className="btn" onClick={onClose} disabled={busy}>
              Cancel
            </button>
          </div>
        </>
      )}
    </Modal>
  )
}
