import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { getPlayerDetail, getSimilarPlayers, addPlayerAlias, getPlayerAliases, putPlayerEmail, sendPlayerMissingDeckLinks } from '../api'
import type { PlayerDetail as PlayerDetailData } from '../api'
import { useAuth } from '../contexts/AuthContext'
import { useFetch } from '../hooks/useFetch'
import PageError from '../components/PageError'
import PageSkeleton from '../components/PageSkeleton'
import { reportError } from '../utils'

export default function PlayerDetail() {
  const { playerName } = useParams<{ playerName: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const { data, loading, error, refetch } = useFetch<PlayerDetailData>(
    () => (playerName ? getPlayerDetail(decodeURIComponent(playerName)) : Promise.reject(new Error('Missing player name'))),
    [playerName ?? '']
  )
  const [similarPlayers, setSimilarPlayers] = useState<string[]>([])
  const [aliases, setAliases] = useState<Record<string, string>>({})
  const [mergeLoading, setMergeLoading] = useState(false)
  const [emailModalOpen, setEmailModalOpen] = useState(false)
  const [emailValue, setEmailValue] = useState('')
  const [savingEmail, setSavingEmail] = useState(false)
  const [sendingMissingLinks, setSendingMissingLinks] = useState(false)

  useEffect(() => {
    if (error) toast.error(reportError(new Error(error)))
  }, [error])

  useEffect(() => {
    if (!data?.player) return
    getSimilarPlayers(data.player, 10).then((r) => setSimilarPlayers(r.similar.filter((s) => s !== data.player)))
    getPlayerAliases().then((r) => setAliases(r.aliases))
  }, [data?.player])

  if (loading) return <PageSkeleton titleWidth={200} blocks={2} />
  if (error) {
    return (
      <PageError message={error} title="Player" onRetry={() => refetch()} />
    )
  }
  if (!data) {
    toast.error('Player not found')
    return (
      <div>
        <h1 className="page-title">Player</h1>
        <div className="chart-container" style={{ textAlign: 'center', padding: '2rem' }}>
          <p style={{ color: 'var(--text-muted)' }}>Player not found.</p>
          <button type="button" className="btn" style={{ marginTop: '1rem' }} onClick={() => navigate('/players')}>
            Back to Players
          </button>
        </div>
      </div>
    )
  }

  return (
    <div>
      <button className="btn" style={{ marginBottom: '1rem' }} onClick={() => navigate(-1)}>
        Back
      </button>

      <h1 className="page-title">{data.player}</h1>

      <div className="stat-card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: '1rem' }}>
          <div>
            <div className="label">Wins</div>
            <div>{data.wins}</div>
          </div>
          <div>
            <div className="label">Top 2</div>
            <div>{data.top2}</div>
          </div>
          <div>
            <div className="label">Top 4</div>
            <div>{data.top4}</div>
          </div>
          <div>
            <div className="label">Top 8</div>
            <div>{data.top8}</div>
          </div>
          <div>
            <div className="label">Points</div>
            <div>{data.points.toFixed(1)}</div>
          </div>
          <div>
            <div className="label">Decks</div>
            <div>{data.deck_count}</div>
          </div>
        </div>
      </div>

      {user === 'admin' && (
        <div className="chart-container" style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ margin: '0 0 0.5rem' }}>Email</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '0.75rem' }}>
            Stored email is used when sending one-time deck or feedback links from an event. Value is never shown.
          </p>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
              {data.has_email ? 'Email set' : 'Email not set'}
            </span>
            <button type="button" className="btn" onClick={() => { setEmailValue(''); setEmailModalOpen(true) }}>
              Set email
            </button>
            {data.has_email && (
              <button
                type="button"
                className="btn"
                disabled={sendingMissingLinks}
                onClick={async () => {
                  if (!data?.player) return
                  setSendingMissingLinks(true)
                  try {
                    const res = await sendPlayerMissingDeckLinks(data.player)
                    if (res.sent > 0) {
                      toast.success('Email sent with links to upload missing decks.')
                    } else {
                      toast.success(res.message ?? 'No missing decks for this player.')
                    }
                  } catch (e) {
                    toast.error(reportError(e as Error))
                  } finally {
                    setSendingMissingLinks(false)
                  }
                }}
              >
                {sendingMissingLinks ? 'Sending…' : 'Email missing deck links'}
              </button>
            )}
          </div>
        </div>
      )}

      {user === 'admin' && similarPlayers.length > 0 && (
        <div className="chart-container" style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ margin: '0 0 0.5rem' }}>Merge players</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '0.75rem' }}>
            These players have similar names. Merge them into &quot;{data?.player}&quot; to combine stats.
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
            {similarPlayers.map((name) => (
              <span
                key={name}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  padding: '0.25rem 0.5rem',
                  background: aliases[name] ? 'rgba(0, 186, 124, 0.2)' : 'var(--bg-hover)',
                  borderRadius: 6,
                  fontSize: '0.9rem',
                }}
              >
                {name}
                {aliases[name] ? (
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>→ {aliases[name]}</span>
                ) : (
                  <button
                    type="button"
                    className="btn"
                    style={{ padding: '0.15rem 0.4rem', fontSize: '0.75rem' }}
                    disabled={mergeLoading}
                    onClick={async () => {
                      setMergeLoading(true)
                      try {
                        await addPlayerAlias(name, data!.player)
                        setAliases((a) => ({ ...a, [name]: data!.player }))
                        navigate(0)
                      } finally {
                        setMergeLoading(false)
                      }
                    }}
                  >
                    Merge into {data?.player}
                  </button>
                )}
              </span>
            ))}
          </div>
        </div>
      )}

      {emailModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="set-email-title"
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
          onClick={(e) => e.target === e.currentTarget && setEmailModalOpen(false)}
        >
          <div
            className="card"
            style={{
              maxWidth: 400,
              width: '100%',
              padding: '1.5rem',
              borderRadius: 12,
              background: 'var(--bg-card)',
              boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="set-email-title" style={{ marginTop: 0, marginBottom: '1rem' }}>Set player email</h2>
            <p style={{ marginBottom: '0.5rem', fontWeight: 600 }}>{data?.player}</p>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
              Enter email for this player. Leave empty to remove. Stored value is never shown.
            </p>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', marginBottom: '1rem' }}>
              <span className="label">Email</span>
              <input
                type="email"
                value={emailValue}
                onChange={(e) => setEmailValue(e.target.value)}
                placeholder="player@example.com"
                style={{ width: '100%', boxSizing: 'border-box' }}
                aria-label="Email address"
              />
            </label>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                type="button"
                className="btn btn-primary"
                disabled={savingEmail}
                onClick={async () => {
                  if (!data?.player) return
                  setSavingEmail(true)
                  try {
                    await putPlayerEmail(data.player, emailValue.trim())
                    setEmailModalOpen(false)
                    toast.success(emailValue.trim() ? 'Email saved' : 'Email removed')
                    refetch()
                  } catch (e) {
                    toast.error(reportError(e as Error))
                  } finally {
                    setSavingEmail(false)
                  }
                }}
              >
                {savingEmail ? 'Saving…' : 'Save'}
              </button>
              <button type="button" className="btn" onClick={() => setEmailModalOpen(false)} disabled={savingEmail}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="chart-container">
        <h3 style={{ margin: '0 0 1rem' }}>Decks</h3>
        <div className="table-wrap-outer">
          <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Deck</th>
                <th>Event</th>
                <th>Date</th>
                <th>Rank</th>
              </tr>
            </thead>
            <tbody>
              {data.decks.map((d) => (
                <tr key={d.deck_id} className="clickable" onClick={() => navigate(`/decks/${d.deck_id}`)}>
                  <td>{d.name}</td>
                  <td>{d.event_name}</td>
                  <td>{d.date}</td>
                  <td>{d.rank || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      </div>
    </div>
  )
}
