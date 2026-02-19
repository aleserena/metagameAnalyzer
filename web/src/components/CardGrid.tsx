import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getCardLookup } from '../api'

interface DeckCard {
  qty: number
  card: string
}

interface CardGridProps {
  cards: DeckCard[]
  title?: string
}

export default function CardGrid({ cards, title }: CardGridProps) {
  const [lookup, setLookup] = useState<Record<string, Awaited<ReturnType<typeof getCardLookup>>[string]>>({})
  const [loading, setLoading] = useState(true)

  const aggregated = cards.reduce<Record<string, number>>((acc, { qty, card }) => {
    acc[card] = (acc[card] ?? 0) + qty
    return acc
  }, {})
  const uniqueCards = Object.entries(aggregated)
  const uniqueNames = Object.keys(aggregated)

  useEffect(() => {
    if (uniqueNames.length === 0) {
      setLoading(false)
      return
    }
    getCardLookup(uniqueNames)
      .then(setLookup)
      .catch(() => setLookup({}))
      .finally(() => setLoading(false))
  }, [uniqueNames.join(',')])

  if (loading) return <div className="loading">Loading card images...</div>

  return (
    <div className="chart-container">
      {title && <h3 style={{ margin: '0 0 1rem' }}>{title}</h3>}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
          gap: '0.5rem',
        }}
      >
        {uniqueCards.map(([card, qty]) => {
          const data = lookup[card]
          const img = data?.image_uris?.normal ?? data?.image_uris?.small
          return (
            <Link
              key={card}
              to={`/decks?card=${encodeURIComponent(card)}`}
              style={{
                display: 'block',
                position: 'relative',
                borderRadius: 4,
                overflow: 'hidden',
                background: 'var(--bg-card)',
                textDecoration: 'none',
                color: 'inherit',
                cursor: 'pointer',
              }}
            >
              {img ? (
                <img
                  src={img}
                  alt={card}
                  title={card}
                  style={{
                    width: '100%',
                    height: 'auto',
                    display: 'block',
                  }}
                />
              ) : (
                <div
                  style={{
                    padding: '1rem',
                    fontSize: '0.75rem',
                    color: 'var(--text-muted)',
                    textAlign: 'center',
                  }}
                >
                  {card}
                </div>
              )}
              <span
                style={{
                  position: 'absolute',
                  top: 4,
                  left: 4,
                  background: 'rgba(0,0,0,0.7)',
                  color: 'white',
                  padding: '2px 6px',
                  borderRadius: 4,
                  fontSize: '0.75rem',
                }}
              >
                {qty}
              </span>
            </Link>
          )
        })}
      </div>
    </div>
  )
}
