/**
 * Pure helpers for the Archetype detail page: mana-cost rendering and matchup sorting.
 */
import { WUBRG_ORDER } from './deckUtils'

/** Color distribution (e.g. {W: 3, U: 0, ...}) -> mana-cost string like "{W}{R}" in WUBRG order. */
export function colorDistributionToManaCost(dist: Record<string, number> | null | undefined): string {
  if (!dist) return ''
  const colors = WUBRG_ORDER.filter((c) => (dist[c] ?? 0) > 0)
  return colors.length ? `{${colors.join('}{')}}` : ''
}

export type MatchupSortKey = 'opponent_archetype' | 'record' | 'win_rate' | 'matches'

export interface ArchetypeMatchupRow {
  opponent_archetype?: string | null
  wins?: number | null
  losses?: number | null
  draws?: number | null
  win_rate?: number | null
  matches?: number | null
}

/**
 * Sort matchup rows by the given key. Ties break on win_rate (respecting `desc`), then opponent
 * name ascending. Returns a new array; input is not mutated.
 */
export function sortArchetypeMatchups<T extends ArchetypeMatchupRow>(
  rows: T[],
  key: MatchupSortKey,
  desc: boolean
): T[] {
  return [...rows].sort((a, b) => {
    let cmp = 0
    if (key === 'opponent_archetype') {
      cmp = (a.opponent_archetype || '').localeCompare(b.opponent_archetype || '')
    } else if (key === 'record' || key === 'matches') {
      const av = (a.wins ?? 0) + (a.losses ?? 0) + (a.draws ?? 0)
      const bv = (b.wins ?? 0) + (b.losses ?? 0) + (b.draws ?? 0)
      cmp = av - bv
    } else if (key === 'win_rate') {
      cmp = (a.win_rate ?? 0) - (b.win_rate ?? 0)
    }
    if (cmp === 0) {
      // stable tiebreakers: win_rate desc, then opponent name asc
      const wr = (a.win_rate ?? 0) - (b.win_rate ?? 0)
      if (wr !== 0) return desc ? -wr : wr
      return (a.opponent_archetype || '').localeCompare(b.opponent_archetype || '')
    }
    return desc ? -cmp : cmp
  })
}
