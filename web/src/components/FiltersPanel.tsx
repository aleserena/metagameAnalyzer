import type { ReactNode } from 'react'

export interface FiltersPanelProps {
  /** Panel content (form groups, buttons, etc.) */
  children: ReactNode
  /** Title shown above the filters (default: "Filters") */
  title?: string
  /** Optional extra class name (e.g. "filters-group" for existing CSS) */
  className?: string
}

const panelStyle: React.CSSProperties = {
  display: 'flex',
  gap: '1rem',
  flexWrap: 'wrap',
  alignItems: 'flex-end',
  padding: '1rem',
  background: 'var(--bg)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  width: '100%',
  boxSizing: 'border-box',
}

const titleStyle: React.CSSProperties = {
  width: '100%',
  fontSize: '0.75rem',
  fontWeight: 600,
  color: 'var(--text-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
}

/**
 * Shared layout for filter sections: card container with optional "Filters" header.
 * Use on Decks, Matchups, and other pages that need a consistent filter panel.
 */
export default function FiltersPanel({
  children,
  title = 'Filters',
  className = 'filters-group',
}: FiltersPanelProps) {
  return (
    <div className={className} style={panelStyle}>
      <span style={titleStyle}>{title}</span>
      {children}
    </div>
  )
}
