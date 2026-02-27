import { useEffect, useRef, type ReactNode, type RefObject } from 'react'

export interface ModalProps {
  /** Modal content */
  children: ReactNode
  /** Called when user requests close (escape, overlay click, or explicit close button) */
  onClose: () => void
  /** Optional title shown at top of the modal */
  title?: string
  /** Optional id for aria-labelledby */
  titleId?: string
  /** Max width of the content area (default 420) */
  size?: 'sm' | 'md' | 'lg' | number
  /** When true, use danger styling for header/actions (e.g. delete confirmations) */
  danger?: boolean
  /** If true, clicking the overlay does not call onClose */
  closeOnOverlayClick?: boolean
  /** Optional ref forwarded to the content wrapper (for focus management) */
  contentRef?: RefObject<HTMLDivElement>
}

const sizeMap = { sm: 360, md: 420, lg: 560 }

/**
 * Generic modal: overlay, scroll lock, escape key, optional title and close-on-overlay.
 * Use for confirmations, forms, and dialogs across UploadDeck, EventDetail, DeckDetail, etc.
 */
export default function Modal({
  children,
  onClose,
  title,
  titleId = 'modal-title',
  size = 'md',
  danger = false,
  closeOnOverlayClick = true,
  contentRef,
}: ModalProps) {
  const overlayRef = useRef<HTMLDivElement>(null)
  const contentRefInternal = useRef<HTMLDivElement>(null)
  const contentRefToUse = contentRef ?? contentRefInternal

  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (closeOnOverlayClick && e.target === overlayRef.current) onClose()
  }

  const maxWidth = typeof size === 'number' ? size : sizeMap[size]

  return (
    <div
      ref={overlayRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby={title ? titleId : undefined}
      onClick={handleOverlayClick}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 10000,
        padding: '1rem',
        overflow: 'auto',
      }}
    >
      <div
        ref={contentRefToUse}
        style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 12,
          maxWidth,
          width: '100%',
          maxHeight: 'calc(100vh - 2rem)',
          overflow: 'auto',
          boxShadow: '0 8px 32px rgba(0,0,0,0.2)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {title && (
          <div
            id={titleId}
            style={{
              padding: '1rem 1.25rem',
              borderBottom: '1px solid var(--border)',
              fontWeight: 600,
              fontSize: '1rem',
              color: danger ? 'var(--danger, #e53e3e)' : 'var(--text)',
            }}
          >
            {title}
          </div>
        )}
        <div style={{ padding: title ? '1.25rem' : '1rem' }}>{children}</div>
      </div>
    </div>
  )
}
