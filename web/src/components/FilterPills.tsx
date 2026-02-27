import ManaSymbols from './ManaSymbols'
import { COLOR_OPTIONS, CMC_OPTIONS, TYPE_OPTIONS, FILTER_SYMBOL_SIZE } from '../lib/topCards'

const pillBaseStyle: React.CSSProperties = {
  borderRadius: 999,
  padding: '0.1rem 0.4rem',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
  opacity: 0.9,
  cursor: 'pointer',
  border: '1px solid var(--border)',
  background: 'transparent',
  color: 'var(--text)',
  fontSize: '0.8rem',
}

function pillActiveStyle(): React.CSSProperties {
  return {
    border: '1px solid var(--accent)',
    background: 'var(--accent-soft, var(--accent))',
    opacity: 1,
  }
}

export interface ColorFilterPillsProps {
  selected: string[]
  onChange: (value: string[]) => void
  disabled?: boolean
  size?: number
}

export function ColorFilterPills({
  selected,
  onChange,
  disabled = false,
  size = FILTER_SYMBOL_SIZE,
}: ColorFilterPillsProps) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', alignItems: 'center' }}>
      {COLOR_OPTIONS.map((opt) => {
        const active = selected.includes(opt.value)
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => {
              if (disabled) return
              if (active) {
                onChange(selected.filter((x) => x !== opt.value))
              } else {
                onChange([...selected, opt.value])
              }
            }}
            disabled={disabled}
            title={opt.title}
            style={{
              ...pillBaseStyle,
              ...(active ? pillActiveStyle() : {}),
              cursor: disabled ? 'default' : 'pointer',
            }}
            aria-pressed={active}
          >
            {opt.manaCost ? (
              <ManaSymbols manaCost={opt.manaCost} size={size} />
            ) : (
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: size,
                  height: size,
                  borderRadius: '50%',
                  background: '#c9b037',
                  color: '#1a1a1a',
                  fontSize: 11,
                  fontWeight: 700,
                }}
              >
                M
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

export interface CmcFilterPillsProps {
  selected: number[]
  onChange: (value: number[]) => void
  disabled?: boolean
  size?: number
}

export function CmcFilterPills({
  selected,
  onChange,
  disabled = false,
  size = FILTER_SYMBOL_SIZE,
}: CmcFilterPillsProps) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', alignItems: 'center' }}>
      {CMC_OPTIONS.map((opt) => {
        const active = selected.includes(opt)
        return (
          <button
            key={opt}
            type="button"
            onClick={() => {
              if (disabled) return
              if (active) {
                onChange(selected.filter((x) => x !== opt))
              } else {
                onChange([...selected, opt])
              }
            }}
            disabled={disabled}
            title={opt === 5 ? '5+' : `CMC ${opt}`}
            style={{
              ...pillBaseStyle,
              ...(active ? pillActiveStyle() : {}),
              cursor: disabled ? 'default' : 'pointer',
            }}
            aria-pressed={active}
          >
            <ManaSymbols manaCost={`{${opt}}`} size={size} />
          </button>
        )
      })}
    </div>
  )
}

export interface TypeFilterPillsProps {
  selected: string[]
  onChange: (value: string[]) => void
  disabled?: boolean
}

export function TypeFilterPills({
  selected,
  onChange,
  disabled = false,
}: TypeFilterPillsProps) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', alignItems: 'center' }}>
      {TYPE_OPTIONS.map((opt) => {
        const active = selected.includes(opt)
        return (
          <button
            key={opt}
            type="button"
            onClick={() => {
              if (disabled) return
              if (active) {
                onChange(selected.filter((x) => x !== opt))
              } else {
                onChange([...selected, opt])
              }
            }}
            disabled={disabled}
            style={{
              ...pillBaseStyle,
              ...(active ? { ...pillActiveStyle(), color: '#ffffff' } : {}),
              cursor: disabled ? 'default' : 'pointer',
            }}
            aria-pressed={active}
          >
            {opt}
          </button>
        )
      })}
    </div>
  )
}
