import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ManaSymbols from './ManaSymbols'

describe('ManaSymbols', () => {
  it('renders correct number of img tags for {W}{U}{B}', () => {
    render(<ManaSymbols manaCost="{W}{U}{B}" />)
    const imgs = screen.getAllByRole('img')
    expect(imgs).toHaveLength(3)
  })

  it('returns null for empty manaCost', () => {
    const { container } = render(<ManaSymbols manaCost="" />)
    expect(container.firstChild).toBeNull()
  })

  it('renders span with text when no symbols match', () => {
    render(<ManaSymbols manaCost="X" />)
    expect(screen.getByText('X')).toBeInTheDocument()
  })
})
