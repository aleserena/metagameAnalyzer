interface PageErrorProps {
  message: string
  title?: string
  onRetry?: () => void
  retryLabel?: string
  /** Extra actions (e.g. "Back to list" link) shown after retry button */
  extraActions?: React.ReactNode
}

/**
 * Inline error state for pages: message + optional Retry button.
 * Use when initial load fails; toasts can remain for transient errors.
 */
export function PageError({ message, title, onRetry, retryLabel = 'Try again', extraActions }: PageErrorProps) {
  return (
    <div className="page">
      {title && <h1 className="page-title">{title}</h1>}
      <div className="chart-container page-error-container">
        <p className="page-error-message">{message}</p>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', justifyContent: 'center' }}>
          {onRetry && (
            <button type="button" className="btn" onClick={onRetry}>
              {retryLabel}
            </button>
          )}
          {extraActions}
        </div>
      </div>
    </div>
  )
}

export default PageError
