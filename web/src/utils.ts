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
