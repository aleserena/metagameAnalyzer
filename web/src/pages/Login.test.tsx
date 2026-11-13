import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Login from './Login'
import { AuthProvider } from '../contexts/AuthContext'

const EXPIRED_MESSAGE = 'Your session expired. Log in again to continue.'

function renderLogin() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Login />
      </AuthProvider>
    </MemoryRouter>
  )
}

describe('Login', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.stubGlobal('fetch', vi.fn())
  })

  it('explains that the session expired, once', () => {
    sessionStorage.setItem('session_expired', '1')

    renderLogin()

    expect(screen.getByText(EXPIRED_MESSAGE)).toBeInTheDocument()
    expect(sessionStorage.getItem('session_expired')).toBeNull()
  })

  it('shows no expiry notice on a normal visit', () => {
    renderLogin()

    expect(screen.queryByText(EXPIRED_MESSAGE)).not.toBeInTheDocument()
  })
})
