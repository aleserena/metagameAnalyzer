import type { CSSProperties, ReactNode } from 'react'

/** Shared tooltip container style for all pie charts across the app. */
export const PIE_TOOLTIP_STYLE: CSSProperties = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: '0.75rem 1rem',
  minWidth: 140,
  boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
}

const titleStyle: CSSProperties = {
  fontWeight: 600,
  marginBottom: '0.25rem',
  color: 'var(--text)',
}

const subtitleStyle: CSSProperties = {
  fontSize: '0.875rem',
  color: 'var(--text-muted)',
}

interface PieChartTooltipContentProps {
  title: string
  subtitle?: string
  children?: ReactNode
}

/** Standard pie chart tooltip: title, optional subtitle, optional extra content (e.g. list). */
export function PieChartTooltipContent({ title, subtitle, children }: PieChartTooltipContentProps) {
  return (
    <div style={PIE_TOOLTIP_STYLE}>
      <div style={titleStyle}>{title}</div>
      {subtitle != null && (
        <div style={{ ...subtitleStyle, marginBottom: children ? '0.5rem' : 0 }}>{subtitle}</div>
      )}
      {children}
    </div>
  )
}
