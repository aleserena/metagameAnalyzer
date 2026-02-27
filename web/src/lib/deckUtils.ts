import type { CardLookupResult } from '../api'

export const WUBRG_ORDER = ['W', 'U', 'B', 'R', 'G'] as const

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
