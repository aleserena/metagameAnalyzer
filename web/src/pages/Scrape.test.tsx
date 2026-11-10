import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import Scrape from './Scrape'
import * as api from '../api'

vi.mock('../api', async (orig) => ({
  ...(await orig<typeof import('../api')>()),
  getScrapeStatus: vi.fn(),
  startScrape: vi.fn(),
  stopScrape: vi.fn(),
}))

const running = {
  id: 'j1',
  status: 'running' as const,
  pct: 40,
  messages: ['[2/5] Fetching decks from Event X...'],
  next: 1,
  message: '',
  decks_saved: 0,
  failed_decks: [],
  started_at: '2026-11-10T10:00:00',
  finished_at: null,
}

describe('Scrape page', () => {
  beforeEach(() => vi.clearAllMocks())

  it('reattaches to a scrape that is already running', async () => {
    vi.mocked(api.getScrapeStatus).mockResolvedValue({ job: running })
    render(<MemoryRouter><Scrape /></MemoryRouter>)
    expect(await screen.findByText('[2/5] Fetching decks from Event X...')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /stop/i })).toBeInTheDocument()
  })

  it('shows the idle form when the server has no job', async () => {
    vi.mocked(api.getScrapeStatus).mockResolvedValue({ job: null })
    render(<MemoryRouter><Scrape /></MemoryRouter>)
    await waitFor(() => expect(api.getScrapeStatus).toHaveBeenCalledWith(0))
    expect(screen.getByRole('button', { name: /^run scrape$/i })).toBeEnabled()
  })

  it('stays in the running state after one failed poll', async () => {
    vi.mocked(api.getScrapeStatus)
      .mockResolvedValueOnce({ job: running })
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValue({
        job: { ...running, messages: ['still going'], next: 2 },
      })
    render(<MemoryRouter><Scrape /></MemoryRouter>)
    expect(await screen.findByText('[2/5] Fetching decks from Event X...')).toBeInTheDocument()
    expect(await screen.findByText('still going', {}, { timeout: 6000 })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /stop/i })).toBeInTheDocument()
  }, 10000)
})
