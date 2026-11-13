import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import UploadDeck from './UploadDeck'
import * as api from '../api'

vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api')>()),
  getUploadLinkInfo: vi.fn(),
  getCardLookup: vi.fn(),
  getCardSearch: vi.fn().mockResolvedValue({ data: [] }),
  submitDeckWithUploadLink: vi.fn(),
  submitFeedbackWithUploadLink: vi.fn(),
  submitDecklistWithUploadLink: vi.fn(),
}))

// The real Toaster needs window.matchMedia, which jsdom does not provide.
vi.mock('react-hot-toast', () => ({
  default: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }),
  Toaster: () => null,
}))

function renderAt(token: string) {
  return render(
    <MemoryRouter initialEntries={[`/upload/${token}`]}>
      <Routes>
        <Route path="/upload/:token" element={<UploadDeck />} />
        <Route path="/" element={<div>HOME PAGE</div>} />
      </Routes>
    </MemoryRouter>
  )
}

const httpError = (status: number, message: string) => Object.assign(new Error(message), { status })

describe('UploadDeck link loading', () => {
  beforeEach(() => {
    vi.mocked(api.getUploadLinkInfo).mockReset()
  })

  it('sends the player home when the link really is invalid (404)', async () => {
    vi.mocked(api.getUploadLinkInfo).mockRejectedValue(httpError(404, 'Link already used'))

    renderAt('dead-token')

    await waitFor(() => expect(screen.getByText('HOME PAGE')).toBeInTheDocument())
  })

  it('keeps the player on the page when the server is only busy (429)', async () => {
    vi.mocked(api.getUploadLinkInfo).mockRejectedValue(httpError(429, 'Too many requests. Try again later.'))

    renderAt('good-token')

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByRole('alert')).toHaveTextContent('Too many requests. Try again later.')
    expect(screen.getByRole('alert')).toHaveTextContent('Your link is still valid')
    expect(screen.queryByText('HOME PAGE')).not.toBeInTheDocument()
  })

  it('keeps the player on the page when the request fails without a status (offline, timeout)', async () => {
    vi.mocked(api.getUploadLinkInfo).mockRejectedValue(new Error('Request timed out'))

    renderAt('good-token')

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.queryByText('HOME PAGE')).not.toBeInTheDocument()
  })
})
