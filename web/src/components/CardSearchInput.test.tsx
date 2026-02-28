import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import CardSearchInput from './CardSearchInput'
import * as api from '../api'

vi.mock('../api', () => ({
  getCardSearch: vi.fn(),
}))

describe('CardSearchInput', () => {
  beforeEach(() => {
    vi.mocked(api.getCardSearch).mockResolvedValue({ data: [] })
  })

  it('renders with placeholder and accepts input', () => {
    const onChange = vi.fn()
    vi.mocked(api.getCardSearch).mockResolvedValue({
      data: ['Lightning Bolt', 'Lightning Helix'],
    })
    render(<CardSearchInput value="" onChange={onChange} />)
    const input = screen.getByPlaceholderText('Search card...')
    expect(input).toBeInTheDocument()
    fireEvent.change(input, { target: { value: 'Light' } })
    expect(input).toHaveValue('Light')
  })

  it('shows display value when not open', () => {
    render(<CardSearchInput value="Lightning Bolt" onChange={vi.fn()} />)
    const input = screen.getByPlaceholderText('Search card...')
    expect(input).toHaveValue('Lightning Bolt')
  })
})
