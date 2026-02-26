import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import toast from 'react-hot-toast'
import { getUploadLinkInfo, submitDeckWithUploadLink } from '../api'
import { parseMoxfieldDeckList, formatMoxfieldDeckList } from '../lib/deckListParser'
import { reportError } from '../utils'

export default function UploadDeck() {
  const { token } = useParams<{ token: string }>()
  const [info, setInfo] = useState<{
    event_id: string
    event_name: string
    format_id: string
    date: string
    mode: 'create' | 'update'
    deck_id?: number
    deck?: {
      deck_id: number
      name: string
      player: string
      rank: string
      mainboard: { qty: number; card: string }[]
      sideboard: { qty: number; card: string }[]
      commanders: string[]
    } | null
  } | null>(null)
  const [invalid, setInvalid] = useState(false)
  const [loading, setLoading] = useState(true)
  const [player, setPlayer] = useState('')
  const [deckName, setDeckName] = useState('')
  const [rank, setRank] = useState('')
  const [deckListText, setDeckListText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  useEffect(() => {
    if (!token) {
      setInvalid(true)
      setLoading(false)
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
      })
      .catch(() => setInvalid(true))
      .finally(() => setLoading(false))
  }, [token])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!token || !info) return
    setSubmitting(true)
    try {
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
    } catch (err) {
      toast.error(reportError(err))
    } finally {
      setSubmitting(false)
    }
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

  if (invalid || !token) {
    return (
      <>
        {toaster}
        <div className="page" style={{ maxWidth: 560, margin: '2rem auto' }}>
          <h1 className="page-title">Upload deck</h1>
          <p style={{ color: 'var(--text-muted)' }}>
            This link is invalid or has already been used.
          </p>
          <Link to="/" className="btn" style={{ marginTop: '1rem' }}>
            Go to home
          </Link>
        </div>
      </>
    )
  }

  if (submitted) {
    const isUpdate = info?.mode === 'update'
    return (
      <>
        {toaster}
        <div className="page" style={{ maxWidth: 560, margin: '2rem auto' }}>
          <h1 className="page-title">{isUpdate ? 'Deck updated' : 'Deck submitted'}</h1>
          <p style={{ color: 'var(--text)', marginBottom: '1rem' }}>
            {isUpdate ? 'Your deck was updated successfully.' : 'Your deck was submitted successfully. Thank you!'}
          </p>
          <Link to="/" className="btn">
            Go to home
          </Link>
        </div>
      </>
    )
  }

  return (
    <>
      {toaster}
      <div className="page" style={{ maxWidth: 560, margin: '2rem auto' }}>
      <h1 className="page-title">{info?.mode === 'update' ? 'Update your deck' : 'Upload deck'}</h1>
        {info && (
        <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
          Event: <strong style={{ color: 'var(--text)' }}>{info.event_name}</strong>
          {info.date && ` · ${info.date}`}
          {info.format_id && ` · ${info.format_id}`}
        </p>
      )}
      <form onSubmit={handleSubmit} className="card" style={{ padding: '1.5rem' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
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
          <button type="submit" className="btn" disabled={submitting}>
            {submitting ? (info?.mode === 'update' ? 'Updating…' : 'Submitting…') : (info?.mode === 'update' ? 'Update deck' : 'Submit deck')}
          </button>
        </div>
      </form>
      <p style={{ marginTop: '1rem' }}>
        <Link to="/" style={{ color: 'var(--accent)' }}>
          Back to home
        </Link>
      </p>
      </div>
    </>
  )
}
