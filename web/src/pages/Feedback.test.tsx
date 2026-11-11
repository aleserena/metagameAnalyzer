import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi, it, expect } from 'vitest'
import Feedback from './Feedback'
import * as api from '../api'

vi.mock('../api', async (orig) => ({
  ...(await orig<typeof import('../api')>()),
  getFeedbackCaptcha: vi.fn(),
  submitFeedback: vi.fn(),
}))

it('shows the server question and submits its token', async () => {
  vi.mocked(api.getFeedbackCaptcha).mockResolvedValue({ question: 'What is 7 + 12?', token: 'tok-1' })
  vi.mocked(api.submitFeedback).mockResolvedValue({ url: 'u', number: 1 })
  render(<MemoryRouter><Feedback /></MemoryRouter>)
  await screen.findByText('What is 7 + 12?')
  fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Bug' } })
  fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Details' } })
  fireEvent.change(screen.getByLabelText('What is 7 + 12?'), { target: { value: '19' } })
  fireEvent.click(screen.getByRole('button', { name: /submit feedback/i }))
  await waitFor(() =>
    expect(api.submitFeedback).toHaveBeenCalledWith(
      expect.objectContaining({ captcha_token: 'tok-1', captcha_answer: 19 }),
    ),
  )
})
