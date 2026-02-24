import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import CardHover from './CardHover'
import * as api from '../api'

const routerFuture = { future: { v7_startTransition: true, v7_relativeSplatPath: true } as const }

vi.mock('../api', () => ({
  getCardLookup: vi.fn(),
}))

function wrap(ui: React.ReactElement) {
  return <MemoryRouter {...routerFuture}>{ui}</MemoryRouter>
}

describe('CardHover', () => {
  beforeEach(() => {
    vi.mocked(api.getCardLookup).mockResolvedValue({})
  })

  it('renders children', () => {
    render(wrap(<CardHover cardName="Lightning Bolt">Custom Text</CardHover>))
    expect(screen.getByText('Custom Text')).toBeInTheDocument()
  })

  it('renders cardName when no children', () => {
    render(wrap(<CardHover cardName="Lightning Bolt" />))
    expect(screen.getByText('Lightning Bolt')).toBeInTheDocument()
  })

  it('shows tooltip on hover and calls getCardLookup', async () => {
    vi.useFakeTimers()
    vi.mocked(api.getCardLookup).mockResolvedValue({
      'Lightning Bolt': {
        image_uris: { normal: 'https://example.com/bolt.png' },
      },
    })
    render(wrap(<CardHover cardName="Lightning Bolt">Bolt</CardHover>))
    const span = screen.getByText('Bolt')
    await act(async () => {
      fireEvent.mouseEnter(span)
      await vi.advanceTimersByTimeAsync(350)
    })
    expect(api.getCardLookup).toHaveBeenCalledWith(['Lightning Bolt'])
    expect(screen.getByAltText('Lightning Bolt')).toBeInTheDocument()
    vi.useRealTimers()
  })

  it('renders Link when linkTo=true', () => {
    render(
      wrap(
        <CardHover cardName="Lightning Bolt" linkTo>
          Bolt
        </CardHover>
      )
    )
    const link = screen.getByRole('link', { name: /bolt/i })
    expect(link.getAttribute('href')).toMatch(/\/decks\?card=Lightning.*Bolt/)
  })
})
