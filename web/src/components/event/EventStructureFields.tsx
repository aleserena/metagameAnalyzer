import { BRACKET_SIZES } from '../../lib/matchups'
import type { EventStructure } from '../../types'

export const DEFAULT_BRACKET_SIZE = 16

/** "Structure" select, plus "Bracket size" when single elimination is chosen (event create and edit forms). */
export default function EventStructureFields({
  structure,
  bracketSize,
  onChange,
  disabled,
}: {
  structure: EventStructure
  bracketSize: number | null
  onChange: (structure: EventStructure, bracketSize: number | null) => void
  disabled?: boolean
}) {
  return (
    <>
      <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
        <span className="label">Structure</span>
        <select
          value={structure}
          disabled={disabled}
          onChange={(e) => {
            const next = e.target.value as EventStructure
            onChange(next, next === 'single_elimination' ? bracketSize ?? DEFAULT_BRACKET_SIZE : null)
          }}
        >
          <option value="swiss">Swiss + Top 8</option>
          <option value="single_elimination">Single elimination</option>
        </select>
      </label>
      {structure === 'single_elimination' && (
        <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <span className="label">Bracket size</span>
          <select
            value={bracketSize ?? DEFAULT_BRACKET_SIZE}
            disabled={disabled}
            onChange={(e) => onChange(structure, parseInt(e.target.value, 10))}
            title="Players in the bracket (the player count can stay the league's total)"
          >
            {BRACKET_SIZES.map((n) => (
              <option key={n} value={n}>{n} players</option>
            ))}
          </select>
        </label>
      )}
    </>
  )
}
