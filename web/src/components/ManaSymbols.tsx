const SCRYFALL_SVG_BASE = 'https://svgs.scryfall.io/card-symbols/'

function symbolToSvgUrl(symbol: string): string {
  const code = symbol.replace(/[{}]/g, '').replace(/\//g, '')
  return `${SCRYFALL_SVG_BASE}${code}.svg`
}

interface ManaSymbolsProps {
  manaCost: string
  size?: number
}

export default function ManaSymbols({ manaCost, size = 16 }: ManaSymbolsProps) {
  if (!manaCost) return null
  const parts = manaCost.match(/\{[^}]+\}/g)
  if (!parts) return <span>{manaCost}</span>
  return (
    <span style={{ display: 'inline-flex', gap: 1, alignItems: 'center' }}>
      {parts.map((sym, i) => (
        <img
          key={i}
          src={symbolToSvgUrl(sym)}
          alt={sym}
          title={sym}
          width={size}
          height={size}
          style={{ verticalAlign: 'middle' }}
        />
      ))}
    </span>
  )
}
