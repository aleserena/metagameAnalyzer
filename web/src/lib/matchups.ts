/**
 * Shared matchup result options and normalization for UploadDeck and EventDetail.
 */

export const MATCHUP_RESULT_OPTIONS = [
  { value: 'win', label: 'You win' },
  { value: 'loss', label: 'You lose' },
  { value: 'draw', label: 'Draw' },
  { value: 'intentional_draw', label: 'Intentional draw' },
  { value: 'intentional_draw_win', label: 'Intentional draw (you win)' },
  { value: 'intentional_draw_loss', label: 'Intentional draw (you lose)' },
  { value: 'bye', label: 'Bye' },
  { value: 'drop', label: 'Drop' },
] as const

export type MatchupResultValue = (typeof MATCHUP_RESULT_OPTIONS)[number]['value']

/**
 * Normalize legacy or API result strings to canonical result value.
 * e.g. '2-1' -> 'win', '1-2' -> 'loss', '1-1' -> 'draw'.
 */
export function normalizeMatchResult(raw: string): MatchupResultValue {
  const r = (raw || '').trim().toLowerCase()
  if (r === 'intentional_draw' || r === 'intentional_draw_win' || r === 'intentional_draw_loss') {
    return r
  }
  if (r === 'bye' || r === 'drop') return r
  if (r === 'win' || r === '2-1' || r === '1-0' || r === '2-0') return 'win'
  if (r === 'loss' || r === '1-2' || r === '0-1' || r === '0-2') return 'loss'
  if (r === 'draw' || r === '1-1' || r === '0-0') return 'draw'
  return 'draw'
}

/** True if the result is one of the intentional draw variants */
export function isIntentionalDraw(result: string): boolean {
  return ['intentional_draw', 'intentional_draw_win', 'intentional_draw_loss'].includes(
    (result || '').trim().toLowerCase()
  )
}

/** True if the result is bye (counts as round, not used in matchup calculations) */
export function isBye(result: string): boolean {
  return (result || '').trim().toLowerCase() === 'bye'
}

/** True if the result is drop (player dropped; exempt from expected matchups validation) */
export function isDrop(result: string): boolean {
  return (result || '').trim().toLowerCase() === 'drop'
}

export interface MatchupRow {
  opponent_player: string
  result: string
  intentional_draw: boolean
}

/** Map API matchup item to normalized row (result + intentional_draw flag) */
export function matchupItemToRow(m: { opponent_player?: string; result?: string; intentional_draw?: boolean }): MatchupRow {
  const raw = (m.result || '').trim().toLowerCase()
  const result = normalizeMatchResult(raw)
  return {
    opponent_player: (m.opponent_player ?? '').trim(),
    result,
    intentional_draw: isIntentionalDraw(raw),
  }
}
