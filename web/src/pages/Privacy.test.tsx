import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { it, expect } from 'vitest'
import Privacy from './Privacy'

it('explains what is stored about players and how to ask for a correction or removal', () => {
  render(
    <MemoryRouter>
      <Privacy />
    </MemoryRouter>
  )

  expect(screen.getByRole('heading', { level: 1, name: 'Privacy' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'What this site stores about players' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Asking for a correction or removal' })).toBeInTheDocument()
  expect(screen.getByText(/never shown on the site/i)).toBeInTheDocument()
  // The request goes through the feedback form, whose text is public: the page must say so.
  expect(screen.getByRole('link', { name: 'feedback form' })).toHaveAttribute('href', '/feedback')
  expect(screen.getByText(/the title and description of a feedback message are public/i)).toBeInTheDocument()
})
