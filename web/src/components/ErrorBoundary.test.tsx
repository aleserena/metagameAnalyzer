import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ErrorBoundary from './ErrorBoundary'

function Thrower({ error }: { error: Error }): never {
  throw error
}

function renderWith(error: Error) {
  return render(
    <MemoryRouter>
      <ErrorBoundary>
        <Thrower error={error} />
      </ErrorBoundary>
    </MemoryRouter>,
  )
}

describe('ErrorBoundary', () => {
  afterEach(() => vi.restoreAllMocks())

  it('offers a reload when a code chunk from an old build is missing', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    renderWith(new TypeError('Failed to fetch dynamically imported module: https://x/assets/Events-CmWtiSYD.js'))
    expect(screen.getByText('A new version is available')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument()
    expect(screen.queryByText('Try again')).not.toBeInTheDocument()
  })

  it('shows the generic message for other errors', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    renderWith(new Error('boom'))
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    expect(screen.getByText('Try again')).toBeInTheDocument()
  })
})
