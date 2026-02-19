import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import CardHover from './CardHover'
import * as api from '../api'

vi.mock('../api', () => ({
  getCardLookup: vi.fn(),
}))

describe('CardHover', () => {
  beforeEach(() => {
    vi.mocked(api.getCardLookup).mockResolvedValue({})
  })

  it('renders children', () => {
    render(
      <MemoryRouter>
        <CardHover cardName="Lightning Bolt">Custom Text</CardHover>
      </MemoryRouter>
    )
    expect(screen.getByText('Custom Text')).toBeInTheDocument()
  })

  it('renders cardName when no children', () => {
    render(
      <MemoryRouter>
        <CardHover cardName="Lightning Bolt" />
      </MemoryRouter>
    )
    expect(screen.getByText('Lightning Bolt')).toBeInTheDocument()
  })

  it('shows tooltip on hover and calls getCardLookup', async () => {
    vi.useFakeTimers()
    vi.mocked(api.getCardLookup).mockResolvedValue({
      'Lightning Bolt': {
        image_uris: { normal: 'https://example.com/bolt.png' },
      },
    })
    render(
      <MemoryRouter>
        <CardHover cardName="Lightning Bolt">Bolt</CardHover>
      </MemoryRouter>
    )
    const span = screen.getByText('Bolt')
    fireEvent.mouseEnter(span)
    await vi.advanceTimersByTimeAsync(350)
    expect(api.getCardLookup).toHaveBeenCalledWith(['Lightning Bolt'])
    expect(screen.getByAltText('Lightning Bolt')).toBeInTheDocument()
    vi.useRealTimers()
  })

  it('renders Link when linkTo=true', () => {
    render(
      <MemoryRouter>
        <CardHover cardName="Lightning Bolt" linkTo>
          Bolt
        </CardHover>
      </MemoryRouter>
    )
    const link = screen.getByRole('link', { name: /bolt/i })
    expect(link.getAttribute('href')).toMatch(/\/decks\?card=Lightning.*Bolt/)
  })
})
