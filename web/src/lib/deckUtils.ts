import type { CardLookupResult } from '../api'
import type { ParsedDeckList } from './deckListParser'
import { formatMoxfieldDeckList } from './deckListParser'

export const WUBRG_ORDER = ['W', 'U', 'B', 'R', 'G'] as const

/**
 * Replace card names in a parsed deck with canonical names from lookup when the card
 * was found by flavor_name (or alias); returns normalized parsed deck and formatted text.
 */
export function normalizeDeckListByLookup(
  parsed: ParsedDeckList,
  lookup: Record<string, CardLookupResult>
): { parsed: ParsedDeckList; text: string } {
  const canon = (card: string): string => {
    const entry = lookup[card]
    if (entry?.name && entry.name !== card) return entry.name
    return card
  }
  const commanders = parsed.commanders.map((c) => ({ ...c, card: canon(c.card) }))
  const mainboard = parsed.mainboard.map((c) => ({ ...c, card: canon(c.card) }))
  const sideboard = parsed.sideboard.map((c) => ({ ...c, card: canon(c.card) }))
  const normalized: ParsedDeckList = { commanders, mainboard, sideboard }
  const text = formatMoxfieldDeckList(
    commanders.map((c) => c.card),
    mainboard,
    sideboard
  )
  return { parsed: normalized, text }
}

/**
 * Canonical card name for equality/comparison (double-faced = front face, case-insensitive).
 * Double-faced cards may be stored as full name or front only; treat as same by using front face.
 * Returns lowercase so all card comparisons are case-insensitive across the site.
 */
export function canonicalCardNameForCompare(card: string): string {
  if (card == null || typeof card !== 'string') return ''
  const s = card.trim()
  const i = s.indexOf(' // ')
  const name = i >= 0 ? s.slice(0, i).trim() : s
  return name.toLowerCase()
}

/**
 * EDH archetype: single commander = name; 2+ commanders = "Partner {Colors}" (WUBRG).
 */
export function getEDHArchetype(
  commanders: string[],
  lookup: Record<string, CardLookupResult> | null
): string | undefined {
  if (commanders.length === 0) return undefined
  if (commanders.length === 1) return commanders[0]
  if (!lookup) return undefined
  const colorSet = new Set<string>()
  for (const name of commanders) {
    const entry = lookup[name]
    if (entry?.error) continue
    const ids = entry?.color_identity ?? entry?.colors ?? []
    ids.forEach((c: string) => colorSet.add(c.toUpperCase()))
  }
  const sorted = WUBRG_ORDER.filter((c) => colorSet.has(c)).join('')
  return sorted ? `Partner ${sorted}` : 'Partner'
}
