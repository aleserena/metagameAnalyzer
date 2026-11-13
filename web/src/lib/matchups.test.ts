import { describe, expect, it } from 'vitest'
import {
  apiMatchupsToPhases,
  bracketRoundLabel,
  bracketRounds,
  BRACKET_SIZES,
  expectedBracketMatches,
  heatmapColor,
  isTop8Rank,
  phasesToApiMatchups,
  rankBandUpper,
  swissRoundsForPlayerCount,
  updateMatchupRowField,
  type MatchupRow,
} from './matchups'

describe('heatmapColor', () => {
  it('is red-ish at 0% (low win rate)', () => {
    expect(heatmapColor(0)).toBe('rgba(220,80,80,0.35)')
  })

  it('is yellow-ish at 50%', () => {
    expect(heatmapColor(50)).toBe('rgba(220,220,80,0.35)')
  })

  it('is green-ish at 100% (high win rate)', () => {
    expect(heatmapColor(100)).toBe('rgba(80,220,80,0.35)')
  })

  it('clamps out-of-range values', () => {
    expect(heatmapColor(-20)).toBe(heatmapColor(0))
    expect(heatmapColor(150)).toBe(heatmapColor(100))
  })
})

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

describe('updateMatchupRowField', () => {
  const row = (opponent_player: string, result: string): MatchupRow => ({ opponent_player, result, intentional_draw: false })

  it('selects result bye when opponent Bye is chosen', () => {
    expect(updateMatchupRowField(row('', 'draw'), 'opponent_player', 'Bye')).toMatchObject({ opponent_player: 'Bye', result: 'bye' })
  })

  it('selects opponent Bye when result bye is chosen', () => {
    expect(updateMatchupRowField(row('Alice', 'win'), 'result', 'bye')).toMatchObject({ opponent_player: 'Bye', result: 'bye' })
  })

  it('keeps drop in sync the same way', () => {
    expect(updateMatchupRowField(row('', 'draw'), 'opponent_player', '(drop)')).toMatchObject({ result: 'drop' })
    expect(updateMatchupRowField(row('Alice', 'win'), 'result', 'drop')).toMatchObject({ opponent_player: '(drop)' })
  })

  it('resets the result when switching from Bye to a real opponent', () => {
    expect(updateMatchupRowField(row('Bye', 'bye'), 'opponent_player', 'Alice')).toMatchObject({ opponent_player: 'Alice', result: 'draw' })
  })

  it('clears the opponent when switching from bye to a normal result', () => {
    expect(updateMatchupRowField(row('Bye', 'bye'), 'result', 'win')).toMatchObject({ opponent_player: '', result: 'win' })
  })

  it('leaves normal edits alone', () => {
    expect(updateMatchupRowField(row('Alice', 'win'), 'result', 'loss')).toMatchObject({ opponent_player: 'Alice', result: 'loss' })
    expect(updateMatchupRowField(row('Alice', 'win'), 'opponent_player', 'Bob')).toMatchObject({ opponent_player: 'Bob', result: 'win' })
  })
})

describe('single-elimination brackets (mirrors api/brackets.py)', () => {
  it('lists the valid bracket sizes', () => {
    expect([...BRACKET_SIZES]).toEqual([2, 4, 8, 16, 32, 64, 128])
  })

  it('counts bracket rounds', () => {
    expect([2, 4, 8, 16, 128].map(bracketRounds)).toEqual([1, 2, 3, 4, 7])
  })

  it('maps ranks to their band upper bound', () => {
    expect(['1', '2', '3-4', '5-8', '9-16', '7', '65-128', '', null, 'x'].map(rankBandUpper)).toEqual([
      1, 2, 4, 8, 16, 8, 128, null, null, null,
    ])
  })

  it('expects matches from rank in a 16-player bracket', () => {
    expect(['1', '2', '3-4', '5-8', '9-16', '17-32', '', '7'].map((r) => expectedBracketMatches(r, 16))).toEqual([
      4, 4, 3, 2, 1, 0, 1, 2,
    ])
  })

  it('expects matches from rank in an 8-player bracket', () => {
    expect(['1', '2', '3-4', '5-8', '9-16'].map((r) => expectedBracketMatches(r, 8))).toEqual([3, 3, 2, 1, 0])
  })

  it('labels bracket rounds', () => {
    expect([1, 2, 3, 4].map((r) => bracketRoundLabel(r, 16))).toEqual(['Round of 16', 'Quarterfinal', 'Semifinal', 'Final'])
    expect(bracketRoundLabel(1, 32)).toBe('Round of 32')
    expect(bracketRoundLabel(1, 2)).toBe('Final')
  })

  it('apiMatchupsToPhases puts null-round rows in bracket order when swissRounds is 0', () => {
    const { top8 } = apiMatchupsToPhases(
      [
        { opponent_player: 'A', result: 'win', round: null },
        { opponent_player: 'B', result: 'loss', round: null },
      ],
      0
    )
    expect(top8.map((r) => r.opponent_player)).toEqual(['A', 'B'])
    expect(phasesToApiMatchups([], top8, 0).map((m) => m.round)).toEqual([1, 2])
  })

  it('apiMatchupsToPhases keeps stored bracket rounds in order and adds rows reported against me', () => {
    const { top8 } = apiMatchupsToPhases(
      [{ opponent_player: 'B', result: 'win', round: 2 }],
      0,
      [{ opponent_player: 'A', result: 'win', round: 1 }]
    )
    expect(top8.map((r) => r.opponent_player).sort()).toEqual(['A', 'B'])
  })

  it('phasesToApiMatchups blanks bye opponent in the cut section', () => {
    const top8: MatchupRow[] = [{ opponent_player: 'Bye', result: 'bye', intentional_draw: false, phase: 'top8' }]
    expect(phasesToApiMatchups([], top8, 0)).toEqual([{ opponent_player: '', result: 'bye', round: 1 }])
  })
})
