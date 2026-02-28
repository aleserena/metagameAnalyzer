import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import CardListSection from './CardListSection'

function wrap(ui: React.ReactElement) {
  return <MemoryRouter>{ui}</MemoryRouter>
}

describe('CardListSection', () => {
  it('renders card list entries', () => {
    const cards = [
      { qty: 2, card: 'Lightning Bolt' },
      { qty: 1, card: 'Counterspell' },
    ]
    render(
      wrap(
        <CardListSection
          cards={cards}
          grouped={null}
          groupMode="none"
          sortMode="name"
          getCardHighlight={() => null}
          showVsMetagame={false}
          playRateByCard={{}}
        />
      )
    )
    expect(screen.getByText('Lightning Bolt')).toBeInTheDocument()
    expect(screen.getByText('Counterspell')).toBeInTheDocument()
  })
})
