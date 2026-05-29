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

export type MatchupPhase = 'swiss' | 'top8'

const TOP8_RANKS = new Set(['1', '2', '3-4', '5-8'])

export const MAX_TOP8_MATCHUP_ROWS = 3
export const MAX_MATCHUPS_TOTAL = 12

/**
 * Expected Swiss rounds: 1–2 → 1, 3–4 → 2, 5–8 → 3, etc. (matches api/db.py).
 */
export function swissRoundsForPlayerCount(n: number): number {
  if (n <= 0) return 0
  return Math.max(1, Math.ceil(Math.log2(n)))
}

/** True if rank is top 8: 1, 2, 3-4, or 5-8 (matches analyzer.is_top8). */
export function isTop8Rank(rank: string | undefined | null): boolean {
  const r = (rank || '').trim()
  if (TOP8_RANKS.has(r)) return true
  if (!/^\d+$/.test(r)) return false
  const n = parseInt(r, 10)
  return n >= 1 && n <= 8
}

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
  phase?: MatchupPhase
}

export interface ApiMatchupItem {
  opponent_player?: string
  result?: string
  intentional_draw?: boolean
  round?: number | null
}

export type ApiMatchupPayload = {
  opponent_player: string
  result: string
  round?: number | null
}

/** Map API matchup item to normalized row (result + intentional_draw flag) */
export function matchupItemToRow(m: ApiMatchupItem): MatchupRow {
  const raw = (m.result || '').trim().toLowerCase()
  const result = normalizeMatchResult(raw)
  return {
    opponent_player: (m.opponent_player ?? '').trim(),
    result,
    intentional_draw: isIntentionalDraw(raw),
  }
}

function emptySwissRow(): MatchupRow {
  return { opponent_player: '', result: 'draw', intentional_draw: false, phase: 'swiss' }
}

function matchupKey(opponent: string, round: number | null): string {
  return `${opponent.toLowerCase()}\0${round ?? 'null'}`
}

/**
 * Split API matchups into Swiss and Top 8 UI rows.
 * Legacy rows without round are assigned Swiss rounds 1..n in API order.
 */
export function apiMatchupsToPhases(
  ourMatchups: ApiMatchupItem[],
  swissRounds: number,
  reportedAgainstMe: ApiMatchupItem[] = []
): { swiss: MatchupRow[]; top8: MatchupRow[] } {
  const swiss: MatchupRow[] = []
  const top8: MatchupRow[] = []
  const ownSwissKeys = new Set<string>()
  const ownTop8Keys = new Set<string>()
  /** Opponents we already have in our saved matchups (any phase); blocks orphan reported rows. */
  const ownOpponentNames = new Set<string>()
  let legacyRound = 0

  for (const m of ourMatchups) {
    const row = matchupItemToRow(m)
    let round = m.round ?? null
    if (round == null) {
      legacyRound += 1
      round = legacyRound
    }
    if (row.opponent_player && !isBye(row.result) && !isDrop(row.result)) {
      ownOpponentNames.add(row.opponent_player.toLowerCase())
    }
    if (round <= swissRounds) {
      if (row.opponent_player && !isBye(row.result) && !isDrop(row.result)) {
        ownSwissKeys.add(matchupKey(row.opponent_player, round))
      }
      swiss.push({ ...row, phase: 'swiss' })
    } else {
      if (row.opponent_player && !isBye(row.result) && !isDrop(row.result)) {
        ownTop8Keys.add(matchupKey(row.opponent_player, round))
      }
      top8.push({ ...row, phase: 'top8' })
    }
  }

  for (const m of reportedAgainstMe) {
    const row = matchupItemToRow(m)
    if (!row.opponent_player || isBye(row.result) || isDrop(row.result)) continue
    const round = m.round ?? null
    if (round != null && round > swissRounds) {
      const key = matchupKey(row.opponent_player, round)
      if (!ownTop8Keys.has(key)) {
        ownTop8Keys.add(key)
        top8.push({ ...row, phase: 'top8' })
      }
      continue
    }
    if (ownOpponentNames.has(row.opponent_player.toLowerCase())) continue
    if (round != null) {
      const key = matchupKey(row.opponent_player, round)
      if (ownSwissKeys.has(key)) continue
      ownSwissKeys.add(key)
      swiss.push({ ...row, phase: 'swiss' })
    } else if (
      !swiss.some((s) => s.opponent_player.toLowerCase() === row.opponent_player.toLowerCase())
    ) {
      swiss.push({ ...row, phase: 'swiss' })
    }
  }

  return {
    swiss: swiss.length > 0 ? swiss : [emptySwissRow()],
    top8,
  }
}

/** Build API payload with explicit round numbers for Swiss and Top 8 sections. */
export function phasesToApiMatchups(
  swissRows: MatchupRow[],
  top8Rows: MatchupRow[],
  swissRounds: number
): ApiMatchupPayload[] {
  const out: ApiMatchupPayload[] = []
  let swissIndex = 0
  for (const m of swissRows) {
    if (!(m.opponent_player || '').trim() && !isBye(m.result) && !isDrop(m.result)) continue
    swissIndex += 1
    out.push({
      opponent_player: isBye(m.result) || isDrop(m.result) ? '' : (m.opponent_player || '').trim(),
      result: m.result || 'draw',
      round: swissIndex,
    })
  }
  let top8Index = 0
  for (const m of top8Rows) {
    if (!(m.opponent_player || '').trim() && !isBye(m.result) && !isDrop(m.result)) continue
    top8Index += 1
    out.push({
      opponent_player: (m.opponent_player || '').trim(),
      result: m.result || 'draw',
      round: swissRounds + top8Index,
    })
  }
  return out
}
