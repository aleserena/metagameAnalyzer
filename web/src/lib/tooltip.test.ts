import { describe, expect, it } from 'vitest'
import { getTooltipPosition, TOOLTIP_ESTIMATE, TOOLTIP_PAD } from './tooltip'

function rect(partial: Partial<DOMRect>): DOMRect {
  return { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0, x: 0, y: 0, toJSON: () => ({}), ...partial } as DOMRect
}

describe('getTooltipPosition', () => {
  it('shows below when there is room beneath the cell', () => {
    const pos = getTooltipPosition(rect({ left: 500, width: 40, top: 100, bottom: 140 }), 1200, 800)
    expect(pos.top).toBe(140) // rect.bottom
    expect(pos.transform).toBe('translate(-50%, 8px)')
    expect(pos.left).toBe(520) // centerX = 500 + 20
  })

  it('shows above when the cell is near the bottom of the viewport', () => {
    const pos = getTooltipPosition(rect({ left: 500, width: 40, top: 740, bottom: 780 }), 1200, 800)
    expect(pos.top).toBe(740) // rect.top
    expect(pos.transform).toBe('translate(-50%, calc(-100% - 8px))')
  })

  it('clamps left edge so the tooltip stays on screen', () => {
    const pos = getTooltipPosition(rect({ left: 0, width: 10, top: 50, bottom: 90 }), 1200, 800)
    expect(pos.left).toBe(TOOLTIP_PAD + TOOLTIP_ESTIMATE.width / 2)
  })

  it('clamps right edge so the tooltip stays on screen', () => {
    const pos = getTooltipPosition(rect({ left: 1190, width: 10, top: 50, bottom: 90 }), 1200, 800)
    expect(pos.left).toBe(1200 - TOOLTIP_PAD - TOOLTIP_ESTIMATE.width / 2)
  })
})
