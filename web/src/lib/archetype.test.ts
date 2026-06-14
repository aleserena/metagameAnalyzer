import { describe, expect, it } from 'vitest'
import { colorDistributionToManaCost, sortArchetypeMatchups, type ArchetypeMatchupRow } from './archetype'

describe('colorDistributionToManaCost', () => {
  it('returns empty string for null/undefined or all-zero distributions', () => {
    expect(colorDistributionToManaCost(null)).toBe('')
    expect(colorDistributionToManaCost(undefined)).toBe('')
    expect(colorDistributionToManaCost({ W: 0, U: 0 })).toBe('')
  })

  it('emits present colors in WUBRG order', () => {
    expect(colorDistributionToManaCost({ R: 2, W: 1 })).toBe('{W}{R}')
    expect(colorDistributionToManaCost({ G: 1, U: 3, B: 2 })).toBe('{U}{B}{G}')
  })

  it('handles a single color', () => {
    expect(colorDistributionToManaCost({ U: 5 })).toBe('{U}')
  })
})

describe('sortArchetypeMatchups', () => {
  const rows: ArchetypeMatchupRow[] = [
    { opponent_archetype: 'Bravo', wins: 1, losses: 1, draws: 0, win_rate: 50, matches: 2 },
    { opponent_archetype: 'Alpha', wins: 3, losses: 0, draws: 0, win_rate: 100, matches: 3 },
    { opponent_archetype: 'Charlie', wins: 0, losses: 4, draws: 0, win_rate: 0, matches: 4 },
  ]

  it('does not mutate the input array', () => {
    const copy = [...rows]
    sortArchetypeMatchups(rows, 'win_rate', true)
    expect(rows).toEqual(copy)
  })

  it('sorts by win_rate descending', () => {
    const out = sortArchetypeMatchups(rows, 'win_rate', true)
    expect(out.map((r) => r.opponent_archetype)).toEqual(['Alpha', 'Bravo', 'Charlie'])
  })

  it('sorts by matches ascending', () => {
    const out = sortArchetypeMatchups(rows, 'matches', false)
    expect(out.map((r) => r.matches)).toEqual([2, 3, 4])
  })

  it('sorts by opponent name', () => {
    const out = sortArchetypeMatchups(rows, 'opponent_archetype', false)
    expect(out.map((r) => r.opponent_archetype)).toEqual(['Alpha', 'Bravo', 'Charlie'])
  })

  it('breaks ties on win_rate then name', () => {
    const tied: ArchetypeMatchupRow[] = [
      { opponent_archetype: 'Z', wins: 1, losses: 0, draws: 0, win_rate: 80, matches: 1 },
      { opponent_archetype: 'A', wins: 1, losses: 0, draws: 0, win_rate: 90, matches: 1 },
    ]
    // same 'matches' total -> tiebreak win_rate desc => A (90) before Z (80)
    const out = sortArchetypeMatchups(tied, 'matches', true)
    expect(out.map((r) => r.opponent_archetype)).toEqual(['A', 'Z'])
  })
})
