import type { CardLookupResult } from '../api'
import type { Deck } from '../types'
import type { ParsedDeckList } from './deckListParser'
import { formatMoxfieldDeckList } from './deckListParser'

export const WUBRG_ORDER = ['W', 'U', 'B', 'R', 'G'] as const

/** Editable fields for a deck in the Event detail bulk-edit form. */
export type BulkDeckEdit = { name: string; player: string; rank: string; archetype: string }

/** Seed a bulk-edit row from a deck; archetype falls back to the first commander (EDH). */
export function defaultDeckEdit(d: Deck): BulkDeckEdit {
  return {
    name: d.name ?? '',
    player: d.player ?? '',
    rank: d.rank ?? '',
    archetype: d.archetype ?? (d.commanders?.length ? d.commanders[0] ?? '' : ''),
  }
}

/**
 * Replace card names in a parsed deck with canonical names from lookup when the card
 * was found by flavor_name; returns normalized parsed deck and formatted text.
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

/** Card-search role filter for the secondary commander slot, by partner mechanic. */
export type PartnerRole =
  | 'partner'
  | 'partner_with'
  | 'friends_forever'
  | 'background'
  | 'doctors_companion'
  | 'time_lord_doctor'

export interface PartnerMode {
  /**
   * Role filter to apply to the SECONDARY commander picker, or null when the
   * primary commander has no partner-style ability (secondary stays disabled).
   */
  role: PartnerRole | null
  /** For 'partner_with', the specific named card the primary may pair with. */
  partnerWithName?: string
}

/** Extract the named partner from a "Partner with [name]" oracle line. */
function parsePartnerWithName(oracleText: string): string | undefined {
  const m = oracleText.match(/Partner with ([^(\n]+)/i)
  if (!m) return undefined
  // Strip trailing punctuation/conjunctions ("Partner with X and Y" → keep "X").
  return m[1].replace(/\s+and\s.*$/i, '').replace(/[.,;]\s*$/, '').trim() || undefined
}

/**
 * Inspect a commander's metadata and decide whether a second commander is
 * allowed and, if so, which cards may legally fill that slot. The returned
 * `role` is the filter for the SECONDARY picker (the complementary mechanic for
 * Doctor pairings).
 */
export function getPartnerMode(entry: CardLookupResult | undefined): PartnerMode {
  if (!entry || entry.error) return { role: null }
  const oracle = (entry.oracle_text ?? '').toLowerCase()
  const typeLine = (entry.type_line ?? '').toLowerCase()

  if (oracle.includes('choose a background')) return { role: 'background' }
  if (oracle.includes('partner with ')) {
    return { role: 'partner_with', partnerWithName: parsePartnerWithName(entry.oracle_text ?? '') }
  }
  if (oracle.includes('friends forever')) return { role: 'friends_forever' }
  // A "Doctor's companion" card pairs with a Time Lord Doctor, and vice versa.
  if (oracle.includes("doctor's companion")) return { role: 'time_lord_doctor' }
  if (typeLine.includes('time lord doctor')) return { role: 'doctors_companion' }
  if (/\bpartner\b/.test(oracle)) return { role: 'partner' }
  return { role: null }
}
