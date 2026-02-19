import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { getPlayerDetail, getSimilarPlayers, addPlayerAlias, getPlayerAliases } from '../api'
import { useAuth } from '../contexts/AuthContext'

export default function PlayerDetail() {
  const { playerName } = useParams<{ playerName: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const [data, setData] = useState<Awaited<ReturnType<typeof getPlayerDetail>> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [similarPlayers, setSimilarPlayers] = useState<string[]>([])
  const [aliases, setAliases] = useState<Record<string, string>>({})
  const [mergeLoading, setMergeLoading] = useState(false)

  useEffect(() => {
    if (!playerName) return
    getPlayerDetail(decodeURIComponent(playerName))
      .then(setData)
      .catch((e) => {
        setError(e.message)
        toast.error(e.message)
      })
      .finally(() => setLoading(false))
  }, [playerName])

  useEffect(() => {
    if (!data?.player) return
    getSimilarPlayers(data.player, 10).then((r) => setSimilarPlayers(r.similar.filter((s) => s !== data.player)))
    getPlayerAliases().then((r) => setAliases(r.aliases))
  }, [data?.player])

  if (loading) return <div className="loading">Loading...</div>
  if (error) {
    return (
      <div>
        <h1 className="page-title">Player</h1>
        <div className="chart-container" style={{ textAlign: 'center', padding: '2rem' }}>
          <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>{error}</p>
          <button
            type="button"
            className="btn"
            onClick={() => {
              setError(null)
              setLoading(true)
              getPlayerDetail(decodeURIComponent(playerName!))
                .then(setData)
                .catch((e) => {
                  setError(e.message)
                  toast.error(e.message)
                })
                .finally(() => setLoading(false))
            }}
          >
            Try again
          </button>
        </div>
      </div>
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

      <div className="chart-container">
        <h3 style={{ margin: '0 0 1rem' }}>Decks</h3>
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
  )
}
