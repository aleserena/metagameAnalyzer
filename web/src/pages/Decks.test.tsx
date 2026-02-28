import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Decks from './Decks'
import * as api from '../api'

vi.mock('../api', () => ({
  getDecks: vi.fn(),
  getDuplicateDecks: vi.fn(),
}))
vi.mock('../hooks/useEventMetadata', () => ({
  useEventMetadata: () => ({
    events: [],
    maxDate: null,
    lastEventDate: null,
    error: null,
  }),
}))
vi.mock('../hooks/useDebouncedSearchParams', () => ({
  useDebouncedSearchParams: () => ({
    filters: {},
    setFilter: vi.fn(),
  }),
}))

describe('Decks page', () => {
  beforeEach(() => {
    vi.mocked(api.getDecks).mockResolvedValue({ decks: [], total: 0, skip: 0, limit: 25 })
    vi.mocked(api.getDuplicateDecks).mockResolvedValue({ duplicates: [] })
  })

  it('renders page with Decks heading and filters', async () => {
    render(
      <MemoryRouter>
        <Decks />
      </MemoryRouter>
    )
    expect(await screen.findByRole('heading', { name: 'Decks' })).toBeInTheDocument()
    expect(screen.getByText('Filters')).toBeInTheDocument()
  })
})
