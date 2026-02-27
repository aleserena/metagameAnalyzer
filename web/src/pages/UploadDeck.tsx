import { useEffect, useState } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import toast from 'react-hot-toast'
import { getUploadLinkInfo, submitDeckWithUploadLink, submitFeedbackWithUploadLink, submitDecklistWithUploadLink } from '../api'
import { parseMoxfieldDeckList, formatMoxfieldDeckList } from '../lib/deckListParser'
import { reportError } from '../utils'
import CardSearchInput from '../components/CardSearchInput'

export default function UploadDeck() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()
  const [info, setInfo] = useState<{
    event_id: string
    event_name: string
    format_id: string
    date: string
    mode: 'create' | 'update'
    purpose: 'deck' | 'feedback'
    deck_id?: number
    deck?: {
      deck_id: number
      name: string
      player: string
      rank: string
      mainboard: { qty: number; card: string }[]
      sideboard: { qty: number; card: string }[]
      commanders: string[]
      archetype?: string | null
    } | null
  } | null>(null)
  const [loading, setLoading] = useState(true)
  const [player, setPlayer] = useState('')
  const [deckName, setDeckName] = useState('')
  const [rank, setRank] = useState('')
  const [deckListText, setDeckListText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  // Feedback form state
  const [archetype, setArchetype] = useState('')
  const [feedbackDeckName, setFeedbackDeckName] = useState('')
  const [feedbackRank, setFeedbackRank] = useState('')
  const MATCHUP_RESULT_OPTIONS = [
    { value: 'win', label: 'You win' },
    { value: 'loss', label: 'You lose' },
    { value: 'draw', label: 'Draw' },
    { value: 'intentional_draw', label: 'Intentional draw' },
    { value: 'intentional_draw_win', label: 'Intentional draw (you win)' },
    { value: 'intentional_draw_loss', label: 'Intentional draw (you lose)' },
  ] as const
  const [matchups, setMatchups] = useState<Array<{ opponent_player: string; result: string; intentional_draw: boolean }>>([
    { opponent_player: '', result: 'draw', intentional_draw: false },
  ])
  const [uploadDeckListText, setUploadDeckListText] = useState('')
  const [showUploadDeckModal, setShowUploadDeckModal] = useState(false)
  const [uploadingDeck, setUploadingDeck] = useState(false)

  useEffect(() => {
    if (!token) {
      toast.error('Link invalid or already used.')
      navigate('/', { replace: true })
      return
    }
    getUploadLinkInfo(token)
      .then((data) => {
        setInfo(data)
        if (data.mode === 'update' && data.deck) {
          setPlayer(data.deck.player)
          setDeckName(data.deck.name)
          setRank(data.deck.rank)
          setDeckListText(
            formatMoxfieldDeckList(
              data.deck.commanders || [],
              data.deck.mainboard || [],
              data.deck.sideboard || []
            )
          )
        }
        if (data.purpose === 'feedback' && data.deck) {
          setArchetype(data.deck.archetype ?? (data.deck.commanders?.length ? data.deck.commanders[0] ?? '' : ''))
          setFeedbackDeckName(data.deck.name ?? '')
          setFeedbackRank(data.deck.rank ?? '')
          const deckWithExtras = data.deck as {
            matchups?: Array<{ opponent_player: string; result: string; intentional_draw?: boolean }>
            event_players?: string[]
            opponent_reported_matchups?: Array<{ opponent_player: string; result: string; intentional_draw?: boolean }>
          }
          const ourMatchups = (deckWithExtras.matchups || []).map((m) => {
            const raw = (m.result || '').trim().toLowerCase()
            let result: string = 'draw'
            if (raw === 'intentional_draw' || raw === 'intentional_draw_win' || raw === 'intentional_draw_loss') {
              result = raw
            } else if (raw) {
              if (raw === 'win' || raw === '2-1' || raw === '1-0' || raw === '2-0') result = 'win'
              else if (raw === 'loss' || raw === '1-2' || raw === '0-1' || raw === '0-2') result = 'loss'
              else if (raw === 'draw' || raw === '1-1' || raw === '0-0') result = 'draw'
            }
            return {
              opponent_player: (m.opponent_player ?? '').trim(),
              result,
              intentional_draw: ['intentional_draw', 'intentional_draw_win', 'intentional_draw_loss'].includes(raw),
            }
          })
          const reportedAgainstMe = (deckWithExtras.opponent_reported_matchups || []).map((m) => ({
            opponent_player: (m.opponent_player ?? '').trim(),
            result: (m.result || 'draw').toLowerCase(),
            intentional_draw: Boolean(m.intentional_draw),
          }))
          const byOpponent = new Map<string, { opponent_player: string; result: string; intentional_draw: boolean }>()
          for (const m of reportedAgainstMe) {
            if (m.opponent_player) byOpponent.set(m.opponent_player, m)
          }
          for (const m of ourMatchups) {
            if (m.opponent_player) byOpponent.set(m.opponent_player, m)
          }
          const merged = Array.from(byOpponent.values())
          setMatchups(merged.length > 0 ? merged : [{ opponent_player: '', result: 'draw', intentional_draw: false }])
        }
      })
      .catch(() => {
        toast.error('Link invalid or already used.')
        navigate('/', { replace: true })
      })
      .finally(() => setLoading(false))
  }, [token, navigate])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!token || !info) return
    setSubmitting(true)
    try {
      if (info.purpose === 'feedback') {
        const payload = {
          archetype: archetype.trim(),
          deck_name: feedbackDeckName.trim() || undefined,
          rank: feedbackRank.trim() || undefined,
          matchups: matchups
            .filter((m) => (m.opponent_player || '').trim())
            .map((m) => ({
              opponent_player: m.opponent_player.trim(),
              result: m.result || 'draw',
            })),
        }
        await submitFeedbackWithUploadLink(token, payload)
        setSubmitted(true)
        toast.success('Feedback submitted successfully.')
      } else {
        const parsed = parseMoxfieldDeckList(deckListText)
        const commanders = parsed.commanders.map((c) => c.card)
        await submitDeckWithUploadLink(token, {
          player: player.trim(),
          name: deckName.trim(),
          rank: rank.trim(),
          mainboard: parsed.mainboard,
          sideboard: parsed.sideboard,
          commanders,
        })
        setSubmitted(true)
        toast.success(info.mode === 'update' ? 'Deck updated successfully.' : 'Deck submitted successfully.')
      }
    } catch (err) {
      toast.error(reportError(err))
    } finally {
      setSubmitting(false)
    }
  }

  const addMatchup = () => setMatchups((prev) => (prev.length >= 10 ? prev : [...prev, { opponent_player: '', result: 'draw', intentional_draw: false }]))
  const updateMatchup = (i: number, field: 'opponent_player' | 'result' | 'intentional_draw', value: string | boolean) => {
    setMatchups((prev) => prev.map((m, j) => (j === i ? { ...m, [field]: value } : m)))
  }
  const removeMatchup = (i: number) => setMatchups((prev) => prev.filter((_, j) => j !== i))

  const openUploadDeckModal = () => {
    setUploadDeckListText(info?.deck ? formatMoxfieldDeckList(info.deck.commanders || [], info.deck.mainboard || [], info.deck.sideboard || []) : '')
    setShowUploadDeckModal(true)
  }
  const closeUploadDeckModal = () => {
    setShowUploadDeckModal(false)
    setUploadDeckListText('')
  }
  const handleUploadDeckListSubmit = () => {
    if (!token) return
    const parsed = parseMoxfieldDeckList(uploadDeckListText)
    const mainboard = parsed.mainboard.filter((c) => c.card.trim())
    if (mainboard.length === 0) {
      toast.error('Deck list must contain at least one mainboard card.')
      return
    }
    const commanders = parsed.commanders.map((c) => c.card.trim()).filter(Boolean)
    const sideboard = parsed.sideboard.filter((c) => c.card.trim())
    setUploadingDeck(true)
    submitDecklistWithUploadLink(token, {
      mainboard,
      sideboard,
      commanders: commanders.length > 0 ? commanders : undefined,
    })
      .then(() => {
        closeUploadDeckModal()
        toast.success('Deck list updated')
      })
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setUploadingDeck(false))
  }

  const toaster = (
    <Toaster
      position="top-right"
      toastOptions={{
        duration: 4000,
        style: {
          background: 'var(--bg-card)',
          color: 'var(--text)',
          border: '1px solid var(--border)',
        },
      }}
    />
  )

  if (loading) {
    return (
      <>
        {toaster}
        <div className="page" style={{ maxWidth: 560, margin: '2rem auto' }}>
          <p>Loading…</p>
        </div>
      </>
    )
  }

  if (submitted) {
    const isFeedback = info?.purpose === 'feedback'
    const isUpdate = info?.mode === 'update'
    return (
      <>
        {toaster}
        <div className="page" style={{ maxWidth: 560, margin: '2rem auto' }}>
          <h1 className="page-title">{isFeedback ? 'Feedback submitted' : isUpdate ? 'Deck updated' : 'Deck submitted'}</h1>
          <p style={{ color: 'var(--text)', marginBottom: '1rem' }}>
            {isFeedback ? 'Your event feedback was submitted successfully. Thank you!' : isUpdate ? 'Your deck was updated successfully.' : 'Your deck was submitted successfully. Thank you!'}
          </p>
          <Link to="/" className="btn">
            Go to home
          </Link>
        </div>
      </>
    )
  }

  const isFeedback = info?.purpose === 'feedback'

  return (
    <>
      {toaster}
      <div className="page" style={{ maxWidth: 560, margin: '2rem auto' }}>
      <h1 className="page-title">{isFeedback ? 'Event feedback' : info?.mode === 'update' ? 'Update your deck' : 'Upload deck'}</h1>
        {info && (
        <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
          Event: <strong style={{ color: 'var(--text)' }}>{info.event_name}</strong>
          {info.date && ` · ${info.date}`}
          {info.format_id && ` · ${info.format_id}`}
        </p>
      )}
      <form onSubmit={handleSubmit} className="card" style={{ padding: '1.5rem' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {isFeedback ? (
            <>
              {info?.deck?.player && (
                <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                  <span className="label">Player</span>
                  <span>{info.deck.player}</span>
                </label>
              )}
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="label">Archetype / commander (EDH) *</span>
                {(info?.format_id ?? '').toLowerCase() === 'edh' || (info?.format_id ?? '').toLowerCase() === 'commander' ? (
                  <CardSearchInput
                    value={archetype}
                    onChange={setArchetype}
                    placeholder="Search commander..."
                    aria-label="Archetype (commander)"
                    disabled={submitting}
                  />
                ) : (
                  <input
                    type="text"
                    value={archetype}
                    onChange={(e) => setArchetype(e.target.value)}
                    required
                    placeholder="e.g. Izzet Murktide"
                    disabled={submitting}
                  />
                )}
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="label">Deck name</span>
                <input
                  type="text"
                  value={feedbackDeckName}
                  onChange={(e) => setFeedbackDeckName(e.target.value)}
                  placeholder="Optional"
                  disabled={submitting}
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="label">Rank</span>
                <input
                  type="text"
                  value={feedbackRank}
                  onChange={(e) => setFeedbackRank(e.target.value)}
                  placeholder="e.g. 1, 2, 3-4"
                  disabled={submitting}
                />
              </label>
              <div>
                <button
                  type="button"
                  className="btn"
                  onClick={openUploadDeckModal}
                  disabled={submitting}
                >
                  Upload deck list
                </button>
              </div>
              <div>
                <span className="label" style={{ display: 'block', marginBottom: '0.5rem' }}>Matchups (max 10)</span>
                <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                  Result is for you vs the selected opponent. Use &quot;Intentional draw (you win/lose)&quot; when the result is ID but tiebreakers assign a win or loss.
                </p>
                {matchups.map((m, i) => (
                  <div key={i} style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <select
                      value={m.opponent_player}
                      onChange={(e) => updateMatchup(i, 'opponent_player', e.target.value)}
                      style={{ minWidth: 140 }}
                      disabled={submitting}
                      aria-label="Opponent"
                    >
                      <option value="">Select opponent</option>
                      {((info?.deck as { event_players?: string[] })?.event_players ?? []).map((name) => (
                        <option key={name} value={name}>{name}</option>
                      ))}
                    </select>
                    <select
                      value={m.result || 'draw'}
                      onChange={(e) => updateMatchup(i, 'result', e.target.value)}
                      disabled={submitting}
                      style={{ minWidth: 200 }}
                      aria-label="Result (you vs this opponent)"
                    >
                      {MATCHUP_RESULT_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                    <button type="button" className="btn" style={{ padding: '0.2rem 0.5rem' }} onClick={() => removeMatchup(i)} disabled={submitting}>
                      Remove
                    </button>
                  </div>
                ))}
                <button type="button" className="btn" style={{ marginTop: '0.35rem' }} onClick={addMatchup} disabled={submitting || matchups.length >= 10}>
                  Add matchup
                </button>
              </div>
            </>
          ) : (
            <>
          <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
            <span className="label">Your name</span>
            <input
              type="text"
              value={player}
              onChange={(e) => setPlayer(e.target.value)}
              required
              placeholder="Player name"
              disabled={submitting}
            />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
            <span className="label">Deck name</span>
            <input
              type="text"
              value={deckName}
              onChange={(e) => setDeckName(e.target.value)}
              required
              placeholder="e.g. Izzet Murktide"
              disabled={submitting}
            />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
            <span className="label">Rank</span>
            <input
              type="text"
              value={rank}
              onChange={(e) => setRank(e.target.value)}
              placeholder="e.g. 1, 2, 3-4, 5-8, 9-16, 17-32, 33-64, 65-128"
              disabled={submitting}
            />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
            <span className="label">Deck list</span>
            <textarea
              value={deckListText}
              onChange={(e) => setDeckListText(e.target.value)}
              required
              placeholder="Paste your deck list (Moxfield style):&#10;Mainboard&#10;4 Lightning Bolt&#10;...&#10;&#10;Sideboard&#10;2 Flusterstorm"
              rows={14}
              style={{ fontFamily: 'var(--font-mono, monospace)', resize: 'vertical' }}
              disabled={submitting}
            />
            <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
              Use section headers: Commander, Mainboard, Sideboard. One line per card: &quot;QTY Card name&quot;.
            </span>
          </label>
            </>
          )}
          <button type="submit" className="btn" disabled={submitting}>
            {submitting ? (isFeedback ? 'Submitting…' : info?.mode === 'update' ? 'Updating…' : 'Submitting…') : (isFeedback ? 'Submit feedback' : info?.mode === 'update' ? 'Update deck' : 'Submit deck')}
          </button>
        </div>
      </form>
      <p style={{ marginTop: '1rem' }}>
        <Link to="/" style={{ color: 'var(--accent)' }}>
          Back to home
        </Link>
      </p>

      {isFeedback && showUploadDeckModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="upload-deck-list-title"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '1rem',
          }}
          onClick={(e) => e.target === e.currentTarget && closeUploadDeckModal()}
        >
          <div
            className="card"
            style={{
              maxWidth: 520,
              width: '100%',
              maxHeight: '90vh',
              overflow: 'auto',
              margin: '1.5rem',
              padding: '1.5rem',
              borderRadius: 12,
              background: 'var(--bg-card)',
              boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="upload-deck-list-title" style={{ marginTop: 0, marginBottom: '1rem' }}>
              Upload deck list
            </h2>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '0.75rem' }}>
              Paste a deck list in Moxfield style (section headers: Commander, Mainboard, Sideboard; lines like &quot;4 Lightning Bolt&quot;).
            </p>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', marginBottom: '1rem' }}>
              <span className="label">Deck list</span>
              <textarea
                value={uploadDeckListText}
                onChange={(e) => setUploadDeckListText(e.target.value)}
                placeholder={`Mainboard\n4 Lightning Bolt\n2 Counterspell\n\nSideboard\n2 Flusterstorm`}
                rows={14}
                style={{ width: '100%', boxSizing: 'border-box', fontFamily: 'inherit', fontSize: '0.9rem', resize: 'vertical' }}
                aria-label="Deck list"
              />
            </label>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button type="button" className="btn btn-primary" onClick={handleUploadDeckListSubmit} disabled={uploadingDeck}>
                {uploadingDeck ? 'Uploading…' : 'Upload'}
              </button>
              <button type="button" className="btn" onClick={closeUploadDeckModal} disabled={uploadingDeck}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
      </div>
    </>
  )
}
