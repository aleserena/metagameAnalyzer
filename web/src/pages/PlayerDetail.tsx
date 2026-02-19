import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getPlayerDetail } from '../api'

export default function PlayerDetail() {
  const { playerName } = useParams<{ playerName: string }>()
  const navigate = useNavigate()
  const [data, setData] = useState<Awaited<ReturnType<typeof getPlayerDetail>> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!playerName) return
    getPlayerDetail(decodeURIComponent(playerName))
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [playerName])

  if (loading) return <div className="loading">Loading...</div>
  if (error) return <div className="error">{error}</div>
  if (!data) return <div className="error">Player not found</div>

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
