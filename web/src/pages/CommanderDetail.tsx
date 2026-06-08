import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { getCommanderSynergies } from '../api'
import CardHover from '../components/CardHover'
import Skeleton from '../components/Skeleton'
import { reportError } from '../utils'
import type { CommanderSynergy } from '../types'

const CATEGORY_ORDER = ['Creature', 'Spell', 'Artifact', 'Enchantment', 'Planeswalker', 'Land', 'Other']

export default function CommanderDetail() {
  const { commanderName } = useParams<{ commanderName: string }>()
  const navigate = useNavigate()
  const [data, setData] = useState<CommanderSynergy | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)

  const decoded = commanderName ? decodeURIComponent(commanderName) : ''

  useEffect(() => {
    if (!decoded) return
    setLoading(true)
    setNotFound(false)
    getCommanderSynergies(decoded)
      .then(setData)
      .catch((e: Error) => {
        if (e.message?.toLowerCase().includes('not found') || e.message?.includes('404')) {
          setNotFound(true)
        } else {
          toast.error(reportError(e))
        }
      })
      .finally(() => setLoading(false))
  }, [decoded])

  if (loading) {
    return (
      <div>
        <h1 className="page-title">{decoded || 'Commander'}</h1>
        <div className="chart-container" style={{ marginBottom: '1.5rem' }}>
          <Skeleton height={24} style={{ marginBottom: '0.5rem' }} />
          <Skeleton height={24} style={{ marginBottom: '0.5rem' }} />
          <Skeleton height={24} />
        </div>
      </div>
    )
  }

  if (notFound || !data) {
    return (
      <div>
        <h1 className="page-title">{decoded || 'Commander'}</h1>
        <div className="chart-container" style={{ textAlign: 'center', padding: '2rem' }}>
          <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>
            No EDH decks found for this commander.
          </p>
          <button type="button" className="btn" onClick={() => navigate(-1)}>
            Back
          </button>
        </div>
      </div>
    )
  }

  const sortedCategories = CATEGORY_ORDER.filter((c) => data.shell_composition[c] != null)
    .concat(Object.keys(data.shell_composition).filter((c) => !CATEGORY_ORDER.includes(c)))

  const maxCategoryPct = Math.max(...sortedCategories.map((c) => data.shell_composition[c] ?? 0), 1)

  return (
    <div>
      <button className="btn" style={{ marginBottom: '1rem' }} onClick={() => navigate(-1)}>
        Back
      </button>

      <h1 className="page-title">
        <CardHover cardName={data.commander}>{data.commander}</CardHover>
        <span style={{ fontSize: '1rem', color: 'var(--text-muted)', fontWeight: 400, marginLeft: '0.75rem' }}>
          Commander Synergy
        </span>
      </h1>

      <div className="stat-card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: '1rem' }}>
          <div>
            <div className="label">Decks analyzed</div>
            <div>{data.deck_count}</div>
          </div>
          {data.co_commanders.length > 0 && (
            <div>
              <div className="label">Top co-commander</div>
              <div>
                <CardHover cardName={data.co_commanders[0].name} linkTo>
                  {data.co_commanders[0].name}
                </CardHover>
                <span style={{ color: 'var(--text-muted)', fontSize: '0.85em', marginLeft: '0.4rem' }}>
                  ({data.co_commanders[0].pct}%)
                </span>
              </div>
            </div>
          )}
        </div>
      </div>

      {data.co_commanders.length > 0 && (
        <div className="chart-container" style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ margin: '0 0 0.75rem' }}>Co-commanders</h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
            {data.co_commanders.map((co) => (
              <span
                key={co.name}
                style={{
                  padding: '0.25rem 0.6rem',
                  background: 'var(--bg-hover)',
                  borderRadius: 4,
                  fontSize: '0.875rem',
                  border: '1px solid var(--border)',
                }}
              >
                <CardHover cardName={co.name} linkTo>{co.name}</CardHover>
                <span style={{ color: 'var(--text-muted)', marginLeft: '0.4rem' }}>
                  {co.count} ({co.pct}%)
                </span>
              </span>
            ))}
          </div>
        </div>
      )}

      {sortedCategories.length > 0 && (
        <div className="chart-container" style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ margin: '0 0 0.75rem' }}>Shell Composition</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
            {sortedCategories.map((cat) => {
              const pct = data.shell_composition[cat] ?? 0
              return (
                <div key={cat} style={{ display: 'grid', gridTemplateColumns: '110px 1fr 48px', gap: '0.5rem', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.875rem' }}>{cat}</span>
                  <div style={{ background: 'var(--border)', borderRadius: 3, height: 10, overflow: 'hidden' }}>
                    <div
                      style={{
                        width: `${(pct / maxCategoryPct) * 100}%`,
                        height: '100%',
                        background: 'var(--accent)',
                        borderRadius: 3,
                      }}
                    />
                  </div>
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textAlign: 'right' }}>{pct.toFixed(1)}%</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {data.core_cards.length > 0 && (
        <div className="chart-container" style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ margin: '0 0 0.5rem' }}>Core Cards <span style={{ fontSize: '0.875rem', fontWeight: 400, color: 'var(--text-muted)' }}>(≥75% inclusion)</span></h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '0.25rem 1rem' }}>
            {data.core_cards.map((entry) => (
              <div key={entry.card} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '2px 0' }}>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  <CardHover cardName={entry.card} linkTo>{entry.card}</CardHover>
                </span>
                <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginLeft: '0.5rem', flexShrink: 0 }}>
                  {entry.inclusion_rate_pct}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {data.flex_cards.length > 0 && (
        <div className="chart-container" style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ margin: '0 0 0.5rem' }}>Flex Slots <span style={{ fontSize: '0.875rem', fontWeight: 400, color: 'var(--text-muted)' }}>(20–74% inclusion)</span></h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '0.25rem 1rem' }}>
            {data.flex_cards.map((entry) => (
              <div key={entry.card} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '2px 0' }}>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  <CardHover cardName={entry.card} linkTo>{entry.card}</CardHover>
                </span>
                <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginLeft: '0.5rem', flexShrink: 0 }}>
                  {entry.inclusion_rate_pct}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {data.tech_cards.length > 0 && (
        <div className="chart-container" style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ margin: '0 0 0.5rem' }}>Tech Cards <span style={{ fontSize: '0.875rem', fontWeight: 400, color: 'var(--text-muted)' }}>(overrepresented in top 4 finishes)</span></h3>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-muted)' }}>
                <th style={{ textAlign: 'left', padding: '0.35rem 0.5rem' }}>Card</th>
                <th style={{ textAlign: 'right', padding: '0.35rem 0.5rem' }}>Overall</th>
                <th style={{ textAlign: 'right', padding: '0.35rem 0.5rem' }}>Top 4</th>
                <th style={{ textAlign: 'right', padding: '0.35rem 0.5rem' }}>Delta</th>
              </tr>
            </thead>
            <tbody>
              {data.tech_cards.map((entry) => (
                <tr key={entry.card} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={{ padding: '0.35rem 0.5rem' }}>
                    <CardHover cardName={entry.card} linkTo>{entry.card}</CardHover>
                  </td>
                  <td style={{ textAlign: 'right', padding: '0.35rem 0.5rem', color: 'var(--text-muted)' }}>
                    {entry.overall_rate_pct}%
                  </td>
                  <td style={{ textAlign: 'right', padding: '0.35rem 0.5rem' }}>
                    {entry.top_rate_pct}%
                  </td>
                  <td style={{ textAlign: 'right', padding: '0.35rem 0.5rem', color: 'var(--success)' }}>
                    +{entry.delta_pct}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
