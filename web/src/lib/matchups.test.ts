import { describe, expect, it } from 'vitest'
import {
  apiMatchupsToPhases,
  isTop8Rank,
  phasesToApiMatchups,
  swissRoundsForPlayerCount,
} from './matchups'

describe('swissRoundsForPlayerCount', () => {
  it('matches backend formula', () => {
    expect(swissRoundsForPlayerCount(4)).toBe(2)
    expect(swissRoundsForPlayerCount(8)).toBe(3)
    expect(swissRoundsForPlayerCount(64)).toBe(6)
  })
})

describe('isTop8Rank', () => {
  it('accepts top 8 rank bands', () => {
    expect(isTop8Rank('1')).toBe(true)
    expect(isTop8Rank('5-8')).toBe(true)
    expect(isTop8Rank('8')).toBe(true)
  })
  it('rejects non-top-8 ranks', () => {
    expect(isTop8Rank('9-16')).toBe(false)
    expect(isTop8Rank('17')).toBe(false)
  })
})

describe('apiMatchupsToPhases', () => {
  it('splits Swiss and Top 8 by round number', () => {
    const { swiss, top8 } = apiMatchupsToPhases(
      [
        { opponent_player: 'Bob', result: 'win', round: 1 },
        { opponent_player: 'Bob', result: 'loss', round: 4 },
      ],
      3
    )
    expect(swiss).toHaveLength(1)
    expect(swiss[0].opponent_player).toBe('Bob')
    expect(top8).toHaveLength(1)
    expect(top8[0].opponent_player).toBe('Bob')
  })

  it('does not duplicate a Top 8 opponent into Swiss from reported matchups without round', () => {
    const { swiss, top8 } = apiMatchupsToPhases(
      [{ opponent_player: 'Bob', result: 'win', round: 4 }],
      3,
      [{ opponent_player: 'Bob', result: 'loss' }]
    )
    expect(top8).toHaveLength(1)
    expect(top8[0].opponent_player).toBe('Bob')
    expect(swiss.filter((s) => s.opponent_player === 'Bob')).toHaveLength(0)
  })

  it('places reported Top 8 matchups in the Top 8 section when round is present', () => {
    const { swiss, top8 } = apiMatchupsToPhases(
      [],
      3,
      [{ opponent_player: 'Bob', result: 'loss', round: 4 }]
    )
    expect(swiss.filter((s) => s.opponent_player === 'Bob')).toHaveLength(0)
    expect(top8).toHaveLength(1)
    expect(top8[0].opponent_player).toBe('Bob')
  })
})

describe('phasesToApiMatchups', () => {
  it('assigns Swiss rounds 1..n and Top 8 after Swiss', () => {
    const payload = phasesToApiMatchups(
      [
        { opponent_player: 'Alice', result: 'win', intentional_draw: false },
        { opponent_player: 'Bob', result: 'loss', intentional_draw: false },
      ],
      [{ opponent_player: 'Bob', result: 'win', intentional_draw: false }],
      3
    )
    expect(payload).toEqual([
      { opponent_player: 'Alice', result: 'win', round: 1 },
      { opponent_player: 'Bob', result: 'loss', round: 2 },
      { opponent_player: 'Bob', result: 'win', round: 4 },
    ])
  })
})
