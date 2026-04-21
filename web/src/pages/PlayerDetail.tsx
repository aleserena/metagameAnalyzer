import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { getPlayerDetail, getPlayerDetailById, getPlayerAnalysisById, getPlayerAnalysisByName, getSimilarPlayers, addPlayerAlias, getPlayerAliases, putPlayerEmail, sendPlayerMissingDeckLinks } from '../api'
import type { PlayerAnalysis, PlayerDetail as PlayerDetailData } from '../api'
import { useAuth } from '../contexts/AuthContext'
import { useEventMetadata } from '../hooks/useEventMetadata'
import { useFetch } from '../hooks/useFetch'
import Modal from '../components/Modal'
import PageError from '../components/PageError'
import PageSkeleton from '../components/PageSkeleton'
import PlayerAnalysisCharts from '../components/player/PlayerAnalysisCharts'
import { getDateRangeFromPreset, reportError } from '../utils'
import type { DatePreset } from '../utils'

export default function PlayerDetail() {
  const { playerId: playerIdParam } = useParams<{ playerId: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const { maxDate, lastEventDate, error: eventMetadataError } = useEventMetadata()
  const [dateFrom, setDateFrom] = useState<string | null>(null)
  const [dateTo, setDateTo] = useState<string | null>(null)
  const id = playerIdParam != null ? parseInt(playerIdParam, 10) : NaN
  const isId = !Number.isNaN(id) && String(id) === playerIdParam
  const { data, loading, error, refetch } = useFetch<PlayerDetailData>(
    () => {
      if (!playerIdParam) return Promise.reject(new Error('Missing player'))
      if (isId) return getPlayerDetailById(id, dateFrom, dateTo)
      return getPlayerDetail(decodeURIComponent(playerIdParam), dateFrom, dateTo)
    },
    [playerIdParam ?? '', isId, id, dateFrom, dateTo]
  )
  const analysisKey = data?.player_id != null ? `id:${data.player_id}` : data?.player ? `name:${data.player}` : ''
  const { data: analysis } = useFetch<PlayerAnalysis | null>(
    () => {
      if (data?.player_id != null) return getPlayerAnalysisById(data.player_id, dateFrom, dateTo)
      if (data?.player) return getPlayerAnalysisByName(data.player, dateFrom, dateTo)
      return Promise.resolve(null)
    },
    [analysisKey, dateFrom, dateTo],
  )
  const [similarPlayers, setSimilarPlayers] = useState<string[]>([])
  const [aliases, setAliases] = useState<Record<string, string>>({})
  const [mergeLoading, setMergeLoading] = useState(false)
  const [emailModalOpen, setEmailModalOpen] = useState(false)
  const [emailValue, setEmailValue] = useState('')
  const [savingEmail, setSavingEmail] = useState(false)
  const [sendingMissingLinks, setSendingMissingLinks] = useState(false)
  const playerNotFoundToastShown = useRef(false)

  useEffect(() => {
    playerNotFoundToastShown.current = false
  }, [playerIdParam])

  useEffect(() => {
    if (error) toast.error(reportError(new Error(error)))
  }, [error])

  useEffect(() => {
    if (eventMetadataError) toast.error(reportError(new Error(eventMetadataError)))
  }, [eventMetadataError])

  const setPreset = (preset: DatePreset) => {
    const { dateFrom: from, dateTo: to } = getDateRangeFromPreset(maxDate, lastEventDate, preset)
    setDateFrom(from)
    setDateTo(to)
  }

  useEffect(() => {
    if (loading || error || data || !playerIdParam) return
    if (playerNotFoundToastShown.current) return
    playerNotFoundToastShown.current = true
    toast.error('Player not found')
  }, [loading, error, data, playerIdParam])

  // When loaded by name, replace URL with stable ID so bookmark/share uses /players/123
  useEffect(() => {
    if (!data?.player_id || !playerIdParam) return
    const currentIsId = !Number.isNaN(parseInt(playerIdParam, 10)) && String(parseInt(playerIdParam, 10)) === playerIdParam
    if (!currentIsId && playerIdParam !== String(data.player_id)) {
      navigate(`/players/${data.player_id}`, { replace: true })
    }
  }, [data?.player_id, playerIdParam, navigate])

  useEffect(() => {
    if (!data?.player) return
    getSimilarPlayers(data.player, 10)
      .then((r) => setSimilarPlayers(r.similar.filter((s) => s !== data.player)))
      .catch(() => setSimilarPlayers([]))
    getPlayerAliases()
      .then((r) => setAliases(r.aliases))
      .catch(() => setAliases({}))
  }, [data?.player])

  if (loading) return <PageSkeleton titleWidth={200} blocks={2} />
  if (error) {
    return (
      <PageError message={error} title="Player" onRetry={() => refetch()} />
    )
  }
  if (!data) {
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

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <h1 className="page-title" style={{ margin: 0 }}>{data.player}</h1>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Date range:</span>
          <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('all')}>
            All time
          </button>
          <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('thisYear')}>
            This year
          </button>
          <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('6months')}>
            6 months
          </button>
          <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('2months')}>
            2 months
          </button>
          <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('month')}>
            Last month
          </button>
          <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('2weeks')}>
            Last 2 weeks
          </button>
          <button type="button" className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.875rem' }} onClick={() => setPreset('lastEvent')}>
            Last event
          </button>
        </div>
      </div>

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

      {analysis ? <PlayerAnalysisCharts analysis={analysis} /> : null}

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
                      } catch (e) {
                        toast.error(reportError(e as Error))
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
        <Modal
          title="Set player email"
          onClose={() => setEmailModalOpen(false)}
          size={400}
        >
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
        </Modal>
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
