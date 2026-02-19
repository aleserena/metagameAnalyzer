/** Parse DD/MM/YY to sortable key (YYMMDD) for comparison */
export function dateSortKey(ddMmYy: string): string {
  const [d, m, y] = ddMmYy.split('/').map(Number)
  const yy = String(y < 100 ? 2000 + y : y).slice(-2)
  const mm = String(m || 0).padStart(2, '0')
  const dd = String(d || 0).padStart(2, '0')
  return yy + mm + dd
}

/** Check if date (DD/MM/YY) is within [from, to] inclusive */
export function dateInRange(date: string, from: string | null, to: string | null): boolean {
  if (!from && !to) return true
  const key = dateSortKey(date)
  if (!/^\d{6}$/.test(key)) return true
  const keyInt = parseInt(key, 10)
  if (from) {
    const fromKey = dateSortKey(from)
    if (/^\d{6}$/.test(fromKey) && keyInt < parseInt(fromKey, 10)) return false
  }
  if (to) {
    const toKey = dateSortKey(to)
    if (/^\d{6}$/.test(toKey) && keyInt > parseInt(toKey, 10)) return false
  }
  return true
}

/** Parse DD/MM/YY to Date; subtract days; return DD/MM/YY */
export function dateMinusDays(ddMmYy: string, days: number): string {
  const [d, m, y] = ddMmYy.split('/').map(Number)
  const year = y < 100 ? 2000 + y : y
  const date = new Date(year, m - 1, d)
  date.setDate(date.getDate() - days)
  const dd = String(date.getDate()).padStart(2, '0')
  const mm = String(date.getMonth() + 1).padStart(2, '0')
  const yy = String(date.getFullYear()).slice(-2)
  return `${dd}/${mm}/${yy}`
}

const PLURAL_MAP: Record<string, string> = {
  Sorcery: 'Sorceries',
  Other: 'Other',
}

export function pluralizeType(name: string): string {
  return PLURAL_MAP[name] ?? `${name}s`
}
