import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { AuthProvider, useAuth } from './AuthContext'

function TestConsumer() {
  const { user, loading, login, logout } = useAuth()
  if (loading) return <span>Loading...</span>
  return (
    <div>
      <span data-testid="user">{user ?? 'none'}</span>
      <button type="button" onClick={() => login('secret')}>Login</button>
      <button type="button" onClick={logout}>Logout</button>
    </div>
  )
}

describe('AuthContext', () => {
  const originalFetch = globalThis.fetch
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, opts?: RequestInit) => {
        if (url.includes('/auth/login')) {
          const body = opts?.body ? JSON.parse(opts.body as string) : {}
          if (body.password === 'secret') {
            return Promise.resolve(
              new Response(JSON.stringify({ token: 'fake-jwt', user: 'admin' }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
              })
            )
          }
          return Promise.resolve(
            new Response(JSON.stringify({ detail: 'Invalid password' }), { status: 401 })
          )
        }
        if (url.includes('/auth/me')) {
          const auth = (opts?.headers as Record<string, string>)?.Authorization
          if (auth === 'Bearer fake-jwt') {
            return Promise.resolve(
              new Response(JSON.stringify({ user: 'admin' }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
              })
            )
          }
          return Promise.resolve(new Response(null, { status: 401 }))
        }
        return (originalFetch as typeof fetch)(url, opts)
      })
    )
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows loading then user state', async () => {
    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    )
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
    })
    expect(screen.getByTestId('user')).toHaveTextContent('none')
  })

  it('login sets user to admin and logout clears', async () => {
    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    )
    await waitFor(() => {
      expect(screen.getByTestId('user')).toHaveTextContent('none')
    })
    fireEvent.click(screen.getByRole('button', { name: 'Login' }))
    await waitFor(() => {
      expect(screen.getByTestId('user')).toHaveTextContent('admin')
    })
    fireEvent.click(screen.getByRole('button', { name: 'Logout' }))
    expect(screen.getByTestId('user')).toHaveTextContent('none')
  })
})
