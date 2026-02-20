import { useState, useCallback, useRef, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { getCardLookup } from '../api'
import type { CardLookupResult } from '../api'

const lookupCache: Record<string, CardLookupResult> = {}

const CARD_W = 223
const CARD_H = 311
const DFC_W = 210
const DFC_H = 293
const DFC_GAP = 10
const OFFSET = 15

interface CardHoverProps {
  cardName: string
  children?: React.ReactNode
  linkTo?: boolean
}

function getFaceUrl(face: { image_uris?: { large?: string; normal?: string; small?: string } }): string | null {
  return face?.image_uris?.large ?? face?.image_uris?.normal ?? face?.image_uris?.small ?? null
}

export default function CardHover({ cardName, children, linkTo = false }: CardHoverProps) {
  const cached = lookupCache[cardName]
  const isDfc = (cached?.card_faces?.length ?? 0) >= 2
  const defaultImg = cached && !isDfc ? (cached.image_uris?.normal ?? cached.image_uris?.small ?? null) : null
  const defaultDfcUrls = cached?.card_faces?.length >= 2
    ? cached.card_faces.map((f) => getFaceUrl(f))
    : []

  const [img, setImg] = useState<string | null>(defaultImg)
  const [dfcUrls, setDfcUrls] = useState<(string | null)[]>(defaultDfcUrls)
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const [visible, setVisible] = useState(false)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const fetchImage = useCallback(() => {
    const cached = lookupCache[cardName]
    const faces = cached?.card_faces
    const isDfc = (faces?.length ?? 0) >= 2

    if (cached) {
      if (isDfc && faces) {
        setImg(null)
        setDfcUrls(faces.map((f) => getFaceUrl(f)))
      } else {
        setDfcUrls([])
        setImg(cached.image_uris?.normal ?? cached.image_uris?.small ?? null)
      }
      return
    }
    getCardLookup([cardName]).then((res) => {
      const c = res[cardName]
      if (c) {
        lookupCache[cardName] = c
        const faces = c.card_faces
        if ((faces?.length ?? 0) >= 2 && faces) {
          setImg(null)
          setDfcUrls(faces.map((f) => getFaceUrl(f)))
        } else {
          setDfcUrls([])
          const url = c.image_uris?.normal ?? c.image_uris?.small
          if (url) setImg(url)
        }
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

  const showDfc = (dfcUrls[0] || dfcUrls[1]) && dfcUrls.length >= 2
  const tooltipW = showDfc ? DFC_W * 2 + DFC_GAP : CARD_W
  const tooltipH = showDfc ? DFC_H : CARD_H

  const tooltipStyle = useMemo(() => {
    const vw = window.innerWidth
    const vh = window.innerHeight
    let left = pos.x + OFFSET
    let top = pos.y + OFFSET

    if (left + tooltipW + OFFSET > vw) {
      left = pos.x - tooltipW - OFFSET
    }
    if (top + tooltipH + OFFSET > vh) {
      top = pos.y - tooltipH - OFFSET
    }
    if (left < 0) left = OFFSET
    if (top < 0) top = OFFSET

    return { position: 'fixed' as const, left, top, zIndex: 9999, pointerEvents: 'none' as const }
  }, [pos.x, pos.y, tooltipW, tooltipH])

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
          {showDfc ? (
            <div
              style={{
                display: 'flex',
                gap: DFC_GAP,
                borderRadius: 8,
                boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
              }}
            >
              {dfcUrls.map((url, i) =>
                url ? (
                  <img
                    key={i}
                    src={url}
                    alt={lookupCache[cardName]?.card_faces?.[i]?.name ?? cardName}
                    style={{
                      width: DFC_W,
                      height: DFC_H,
                      borderRadius: 6,
                      display: 'block',
                    }}
                  />
                ) : (
                  <div
                    key={i}
                    style={{
                      width: DFC_W,
                      height: DFC_H,
                      borderRadius: 6,
                      background: 'var(--bg-card)',
                      border: '1px solid var(--border)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '0.75rem',
                      color: 'var(--text-muted)',
                    }}
                  >
                    —
                  </div>
                )
              )}
            </div>
          ) : img ? (
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
