/**
 * Deck list parsing (Moxfield-style): section headers and "QTY Card" lines.
 * Section headers: Commander/Mainboard/Sideboard (with optional trailing colon).
 * Card lines may include (SET) number and *F* foiling; only quantity and name are used.
 */

/** Section header words (case-insensitive); optional trailing colon. */
const COMMANDER_HEADERS = /^(commander|edh)\s*:?\s*$/i
const MAINBOARD_HEADERS = /^(mainboard|main deck|maindeck|deck|main)\s*:?\s*$/i
const SIDEBOARD_HEADERS = /^(sideboard|sb|side board)\s*:?\s*$/i

export function isSectionHeader(line: string): 'commander' | 'main' | 'side' | null {
  const t = line.trim()
  if (COMMANDER_HEADERS.test(t)) return 'commander'
  if (MAINBOARD_HEADERS.test(t)) return 'main'
  if (SIDEBOARD_HEADERS.test(t)) return 'side'
  return null
}

/**
 * Strip expansion (SET) number and foiling markers from the end of a card line.
 * e.g. "Ashling, the Limitless (ECC) 1 *F*" -> "Ashling, the Limitless"
 */
export function stripSetAndFoiling(card: string): string {
  let s = card.trim()
  // Trailing *F* *C* etc (foil/etched indicators) — strip first so (SET) num is at end
  s = s.replace(/\s*\*\w*\*(\s*\*\w*\*)*\s*$/g, '').trim()
  // Trailing (SET) or (SET) 123
  s = s.replace(/\s*\([A-Za-z0-9]{2,5}\)\s*\d*\s*$/i, '').trim()
  return s
}

export interface ParsedDeckList {
  commanders: { qty: number; card: string }[]
  mainboard: { qty: number; card: string }[]
  sideboard: { qty: number; card: string }[]
}

/**
 * Parse deck list: "QTY Card" or "QTYx Card" per line; missing QTY = 1.
 * Card line may include expansion and foiling, e.g. "1 Ashling (ECC) 1 *F*" — only qty and name are used.
 * "Commander" / "Mainboard" / "Sideboard" (and variants, with optional colon) are section headers only.
 */
export function parseMoxfieldDeckList(text: string): ParsedDeckList {
  const commanders: { qty: number; card: string }[] = []
  const mainboard: { qty: number; card: string }[] = []
  const sideboard: { qty: number; card: string }[] = []
  let section: 'commander' | 'main' | 'side' = 'main'
  const withQty = /^(\d+)\s*x?\s*(.+)$/
  const lines = text.split(/\r?\n/)
  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed) continue
    const header = isSectionHeader(trimmed)
    if (header !== null) {
      section = header
      continue
    }
    const m = trimmed.match(withQty)
    const qty = m ? Math.max(1, parseInt(m[1], 10)) : 1
    const rawCard = (m ? m[2] : trimmed).trim()
    const card = stripSetAndFoiling(rawCard)
    if (!card) continue
    if (section === 'commander') commanders.push({ qty, card })
    else if (section === 'main') mainboard.push({ qty, card })
    else sideboard.push({ qty, card })
  }
  return { commanders, mainboard, sideboard }
}

/** Format Commander + Mainboard + Sideboard to text (section headers + "QTY Card" per line). */
export function formatMoxfieldDeckList(
  commanders: string[],
  mainboard: { qty: number; card: string }[],
  sideboard: { qty: number; card: string }[]
): string {
  const parts: string[] = []
  if (commanders?.length) {
    parts.push('Commander')
    parts.push(...commanders.map((c) => `1 ${c}`))
    parts.push('')
  }
  parts.push('Mainboard')
  parts.push(...(mainboard || []).map((c) => `${c.qty} ${c.card}`))
  if (sideboard?.length) {
    parts.push('')
    parts.push('Sideboard')
    parts.push(...sideboard.map((c) => `${c.qty} ${c.card}`))
  }
  return parts.join('\n')
}
