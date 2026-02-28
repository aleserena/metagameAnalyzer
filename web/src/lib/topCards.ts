/**
 * Shared constants and helpers for Top Cards filtering (Metagame, Archetype Detail).
 */

export const TYPE_ORDER = [
  'Land',
  'Creature',
  'Instant',
  'Sorcery',
  'Enchantment',
  'Artifact',
  'Planeswalker',
] as const

/** Returns all card types present in type_line (e.g. "Enchantment Land — Saga" → ["Enchantment", "Land"]). */
export function getCardTypes(typeLine: string | undefined): string[] {
  if (!typeLine) return ['Other']
  const upper = typeLine.toUpperCase()
  const types = TYPE_ORDER.filter((t) => upper.includes(t.toUpperCase()))
  return types.length > 0 ? types : ['Other']
}

export function colorCategory(colors: string[] | undefined): string {
  if (!colors || colors.length === 0) return 'Colorless'
  if (colors.length >= 2) return 'Multicolor'
  return colors[0]!
}

export function cmcBucket(cmc: number | undefined): number {
  if (typeof cmc !== 'number' || cmc < 0) return 0
  return cmc >= 5 ? 5 : cmc
}

export const COLOR_OPTIONS: { value: string; manaCost: string | null; title: string }[] = [
  { value: 'W', manaCost: '{W}', title: 'White' },
  { value: 'U', manaCost: '{U}', title: 'Blue' },
  { value: 'B', manaCost: '{B}', title: 'Black' },
  { value: 'R', manaCost: '{R}', title: 'Red' },
  { value: 'G', manaCost: '{G}', title: 'Green' },
  { value: 'Colorless', manaCost: '{C}', title: 'Colorless' },
  { value: 'Multicolor', manaCost: null, title: 'Multicolor' },
]

export const CMC_OPTIONS = [0, 1, 2, 3, 4, 5] // 5 means 5+

export const TYPE_OPTIONS = [...TYPE_ORDER, 'Other'] as const

export const FILTER_SYMBOL_SIZE = 20

export const TOP_CARDS_PER_PAGE = 50

export interface TopCardItem {
  card: string
  decks: number
  play_rate_pct: number
  total_copies: number
  /** Decks that played this card and made top 8. */
  decks_top8?: number
  /** % of decks that played this card and made top 8 (conversion). */
  conversion_rate_pct?: number
}
