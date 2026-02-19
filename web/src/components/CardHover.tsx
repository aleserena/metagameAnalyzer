import { useState, useCallback, useRef, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { getCardLookup } from '../api'

const lookupCache: Record<string, Awaited<ReturnType<typeof getCardLookup>>[string]> = {}

const CARD_W = 223
const CARD_H = 311
const OFFSET = 15

interface CardHoverProps {
  cardName: string
  children?: React.ReactNode
  linkTo?: boolean
}

export default function CardHover({ cardName, children, linkTo = false }: CardHoverProps) {
  const [img, setImg] = useState<string | null>(lookupCache[cardName]?.image_uris?.normal ?? lookupCache[cardName]?.image_uris?.small ?? null)
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const [visible, setVisible] = useState(false)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const fetchImage = useCallback(() => {
    const cached = lookupCache[cardName]
    const url = cached?.image_uris?.normal ?? cached?.image_uris?.small ?? null
    setImg(url)
    if (cached) return
    getCardLookup([cardName]).then((res) => {
      const c = res[cardName]
      if (c) {
        lookupCache[cardName] = c
        const url = c.image_uris?.normal ?? c.image_uris?.small
        if (url) setImg(url)
      }
    })
  }, [cardName])

  const handleMouseEnter = useCallback(
    (e: React.MouseEvent) => {
      timeoutRef.current = setTimeout(() => {
        setPos({ x: e.clientX, y: e.clientY })
        setVisible(true)
        fetchImage()
      }, 300)
    },
    [fetchImage]
  )

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (visible) setPos({ x: e.clientX, y: e.clientY })
  }, [visible])

  const handleMouseLeave = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
      timeoutRef.current = null
    }
    setVisible(false)
  }, [])

  const tooltipStyle = useMemo(() => {
    const vw = window.innerWidth
    const vh = window.innerHeight
    let left = pos.x + OFFSET
    let top = pos.y + OFFSET

    if (left + CARD_W + OFFSET > vw) {
      left = pos.x - CARD_W - OFFSET
    }
    if (top + CARD_H + OFFSET > vh) {
      top = pos.y - CARD_H - OFFSET
    }
    if (left < 0) left = OFFSET
    if (top < 0) top = OFFSET

    return { position: 'fixed' as const, left, top, zIndex: 9999, pointerEvents: 'none' as const }
  }, [pos.x, pos.y])

  const content = (
    <span
      onMouseEnter={handleMouseEnter}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={{ cursor: 'pointer', textDecoration: 'underline', textDecorationStyle: 'dotted' }}
    >
      {children ?? cardName}
    </span>
  )

  return (
    <>
      {linkTo ? (
        <Link to={`/decks?card=${encodeURIComponent(cardName)}`} style={{ color: 'inherit' }}>
          {content}
        </Link>
      ) : (
        content
      )}
      {visible && (
        <div style={tooltipStyle}>
          {img ? (
            <img
              src={img}
              alt={cardName}
              style={{
                width: CARD_W,
                height: CARD_H,
                borderRadius: 8,
                boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
              }}
            />
          ) : (
            <div
              style={{
                width: CARD_W,
                height: CARD_H,
                borderRadius: 8,
                background: 'var(--bg-card)',
                border: '1px solid var(--border)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '0.875rem',
                color: 'var(--text-muted)',
              }}
            >
              Loading...
            </div>
          )}
        </div>
      )}
    </>
  )
}
