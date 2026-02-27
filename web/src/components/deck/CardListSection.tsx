import type { CardMeta, DeckAnalysis } from '../../api'
import CardHover from '../CardHover'
import ManaSymbols from '../ManaSymbols'
import { pluralizeType } from '../../utils'

export type GroupMode = 'type' | 'cmc' | 'color' | 'none'
export type SortMode = 'name' | 'cmc'

const COLOR_LABELS: Record<string, string> = {
  W: 'White', U: 'Blue', B: 'Black', R: 'Red', G: 'Green',
  C: 'Colorless', M: 'Multicolor', Land: 'Land',
}

export function groupLabel(mode: GroupMode, key: string): string {
  if (mode === 'type') return pluralizeType(key)
  if (mode === 'color') return COLOR_LABELS[key] ?? key
  if (mode === 'cmc') return key === '0' ? 'CMC 0' : `CMC ${key}`
  return key
}

export function getGroupedData(
  analysis: DeckAnalysis | null,
  mode: GroupMode,
  section: 'main' | 'side',
): Record<string, [number, string][]> | null {
  if (!analysis) return null
  if (mode === 'type') return section === 'main' ? analysis.grouped_by_type ?? null : analysis.grouped_by_type_sideboard ?? null
  if (mode === 'cmc') return section === 'main' ? analysis.grouped_by_cmc ?? null : analysis.grouped_by_cmc_sideboard ?? null
  if (mode === 'color') return section === 'main' ? analysis.grouped_by_color ?? null : analysis.grouped_by_color_sideboard ?? null
  return null
}

export function sortEntries(
  entries: [number, string][],
  cardMeta: Record<string, CardMeta> | undefined,
  sortMode: SortMode,
): [number, string][] {
  return [...entries].sort((a, b) => {
    const [, cardA] = a
    const [, cardB] = b
    if (sortMode === 'cmc') {
      const cmcA = cardMeta?.[cardA]?.cmc ?? 99
      const cmcB = cardMeta?.[cardB]?.cmc ?? 99
      if (cmcA !== cmcB) return cmcA - cmcB
    }
    return cardA.localeCompare(cardB, undefined, { sensitivity: 'base' })
  })
}

function CardRow({
  qty, card, meta, highlight, showVsMetagame, playRate,
}: {
  qty: number
  card: string
  meta?: CardMeta
  highlight: string | null
  showVsMetagame: boolean
  playRate?: number
}) {
  const rowClass = [
    'deck-card-row',
    highlight === 'above' ? 'deck-card-row--above' : '',
    highlight === 'below' ? 'deck-card-row--below' : '',
  ].filter(Boolean).join(' ')
  return (
    <div className={rowClass}>
      <span className="qty">{qty}</span>
      <span className="deck-card-name">
        <CardHover cardName={card} linkTo>{card}</CardHover>
      </span>
      <span className="deck-card-meta">
        {meta ? <ManaSymbols manaCost={meta.mana_cost} size={14} /> : null}
        {showVsMetagame && playRate != null && (
          <span className="deck-card-play-rate">{playRate}%</span>
        )}
      </span>
    </div>
  )
}

export interface CardListSectionProps {
  cards: { qty: number; card: string }[]
  grouped: Record<string, [number, string][]> | null
  groupMode: GroupMode
  sortMode: SortMode
  cardMeta?: Record<string, CardMeta>
  getCardHighlight: (card: string) => string | null
  showVsMetagame: boolean
  playRateByCard: Record<string, number>
}

export default function CardListSection({
  cards,
  grouped,
  groupMode,
  sortMode,
  cardMeta,
  getCardHighlight,
  showVsMetagame,
  playRateByCard,
}: CardListSectionProps) {
  const renderCards = (entries: [number, string][]) =>
    sortEntries(entries, cardMeta, sortMode).map(([qty, card]) => (
      <CardRow
        key={card}
        qty={qty}
        card={card}
        meta={cardMeta?.[card]}
        highlight={getCardHighlight(card)}
        showVsMetagame={showVsMetagame}
        playRate={playRateByCard[card]}
      />
    ))

  if (grouped && groupMode !== 'none' && Object.keys(grouped).length > 0) {
    const groups = Object.entries(grouped)
    const midpoint = Math.ceil(
      groups.reduce((s, [, e]) => s + e.length, 0) / 2,
    )
    let count = 0
    let splitIdx = groups.length
    for (let i = 0; i < groups.length; i++) {
      count += groups[i][1].length
      if (count >= midpoint) { splitIdx = i + 1; break }
    }
    const col1 = groups.slice(0, splitIdx)
    const col2 = groups.slice(splitIdx)

    const renderColumn = (grps: [string, [number, string][]][]) =>
      grps.map(([key, entries]) => {
        const total = entries.reduce((s, [q]) => s + q, 0)
        return (
          <div key={key}>
            <div style={{ fontWeight: 600, marginTop: '0.5rem', marginBottom: '0.25rem', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              {groupLabel(groupMode, key)} ({total})
            </div>
            {renderCards(entries)}
          </div>
        )
      })

    return (
      <div className="deck-list-grid">
        <div className="deck-list">{renderColumn(col1)}</div>
        <div className="deck-list">{renderColumn(col2)}</div>
      </div>
    )
  }

  const entries = cards.map((c) => [c.qty, c.card] as [number, string])
  const sorted = sortEntries(entries, cardMeta, sortMode)
  const half = Math.ceil(sorted.length / 2)
  const col1 = sorted.slice(0, half)
  const col2 = sorted.slice(half)
  return (
    <div className="deck-list-grid">
      <div className="deck-list">
        {col1.map(([qty, card]) => (
          <CardRow
            key={card}
            qty={qty}
            card={card}
            meta={cardMeta?.[card]}
            highlight={getCardHighlight(card)}
            showVsMetagame={showVsMetagame}
            playRate={playRateByCard[card]}
          />
        ))}
      </div>
      <div className="deck-list">
        {col2.map(([qty, card]) => (
          <CardRow
            key={card}
            qty={qty}
            card={card}
            meta={cardMeta?.[card]}
            highlight={getCardHighlight(card)}
            showVsMetagame={showVsMetagame}
            playRate={playRateByCard[card]}
          />
        ))}
      </div>
    </div>
  )
}
