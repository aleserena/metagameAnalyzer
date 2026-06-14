/**
 * Viewport-aware tooltip positioning (used by the matchup matrices).
 * Pure: pass viewport dimensions explicitly (defaults to the live window) so it's testable.
 */

export const TOOLTIP_ESTIMATE = { width: 270, height: 100 }
export const TOOLTIP_PAD = 12

export interface TooltipPosition {
  left: number
  top: number
  transform: string
}

/** Position a tooltip near `rect` so it stays inside the viewport (shows above for bottom cells). */
export function getTooltipPosition(
  rect: DOMRect,
  vw: number = window.innerWidth,
  vh: number = window.innerHeight
): TooltipPosition {
  const halfW = TOOLTIP_ESTIMATE.width / 2
  const centerX = rect.left + rect.width / 2
  const left = Math.max(TOOLTIP_PAD + halfW, Math.min(vw - TOOLTIP_PAD - halfW, centerX))
  const showBelow = rect.bottom + 8 + TOOLTIP_ESTIMATE.height <= vh - TOOLTIP_PAD
  if (showBelow) {
    return { left, top: rect.bottom, transform: 'translate(-50%, 8px)' }
  }
  return { left, top: rect.top, transform: 'translate(-50%, calc(-100% - 8px))' }
}
