import type { ReactNode } from 'react'

export interface EmptyStateProps {
  /** Short title (e.g. "No decks yet") */
  title: string
  /** Optional description paragraph */
  description?: string
  /** Primary action (e.g. Link or button) */
  action?: ReactNode
  /** Optional icon or illustration (node or string for emoji) */
  icon?: ReactNode
}

/**
 * Consistent empty state for lists and pages: title, description, primary CTA.
 * Use when there is no data yet (e.g. "Load or scrape data", "No events").
 */
export default function EmptyState({ title, description, action, icon }: EmptyStateProps) {
  return (
    <div
      className="chart-container"
      style={{
        textAlign: 'center',
        padding: '3rem 2rem',
        maxWidth: 480,
        margin: '0 auto',
      }}
    >
      {icon && (
        <div style={{ marginBottom: '1rem', fontSize: '2rem', color: 'var(--text-muted)' }}>
          {typeof icon === 'string' ? icon : icon}
        </div>
      )}
      <p style={{ color: 'var(--text-muted)', marginBottom: '0.5rem', fontSize: '1.1rem' }}>{title}</p>
      {description && (
        <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem', fontSize: '0.9rem' }}>{description}</p>
      )}
      {!description && action && <div style={{ marginTop: '1rem' }}>{action}</div>}
      {description && action && <div style={{ marginTop: '0.5rem' }}>{action}</div>}
    </div>
  )
}
