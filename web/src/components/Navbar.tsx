import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

const baseNavItems = [
  { path: '/', label: 'Dashboard' },
  { path: '/events', label: 'Events' },
  { path: '/metagame', label: 'Metagame' },
  { path: '/archetypes', label: 'Archetypes' },
  { path: '/decks', label: 'Decks' },
  { path: '/decks/compare', label: 'Compare' },
  { path: '/players', label: 'Players' },
]

const adminNavItems = [
  { path: '/scrape', label: 'Scrape' },
  { path: '/settings', label: 'Settings' },
]

export default function Navbar() {
  const location = useLocation()
  const { user, logout } = useAuth()
  const [isOpen, setIsOpen] = useState(false)
  const navItems = [...baseNavItems, ...(user === 'admin' ? adminNavItems : [])]

  useEffect(() => {
    setIsOpen(false)
  }, [location.pathname])

  return (
    <nav className="navbar" aria-label="Main navigation">
      <div className="navbar-header">
        <Link to="/" className="navbar-brand" onClick={() => setIsOpen(false)}>
          MTG Metagame
        </Link>
        <button
          type="button"
          className="navbar-toggle"
          aria-label="Toggle navigation"
          aria-expanded={isOpen}
          onClick={() => setIsOpen((v) => !v)}
        >
          <span className="navbar-toggle-icon" aria-hidden>☰</span>
        </button>
      </div>
      <div className={`navbar-menu ${isOpen ? 'navbar-menu--open' : ''}`}>
        <ul className="navbar-nav">
          {navItems.map(({ path, label }) => {
            const isActive = path === '/events' ? location.pathname.startsWith('/events') : location.pathname === path
            return (
              <li key={path}>
                <Link to={path} className={isActive ? 'nav-link active' : 'nav-link'}>
                  {label}
                </Link>
              </li>
            )
          })}
          {user === 'admin' && (
            <li>
              <button
                type="button"
                className="nav-link nav-link-button"
                onClick={logout}
              >
                Logout
              </button>
            </li>
          )}
        </ul>
      </div>
    </nav>
  )
}
