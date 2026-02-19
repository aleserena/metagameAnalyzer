import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

const baseNavItems = [
  { path: '/', label: 'Dashboard' },
  { path: '/metagame', label: 'Metagame' },
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
  const navItems = [...baseNavItems, ...(user === 'admin' ? adminNavItems : [])]

  return (
    <nav className="navbar">
      <Link to="/" className="navbar-brand">
        MTG Metagame
      </Link>
      <ul className="navbar-nav">
        {navItems.map(({ path, label }) => (
          <li key={path}>
            <Link
              to={path}
              className={location.pathname === path ? 'nav-link active' : 'nav-link'}
            >
              {label}
            </Link>
          </li>
        ))}
        {user === 'admin' ? (
          <li>
            <button
              type="button"
              className="nav-link nav-link-button"
              onClick={logout}
            >
              Logout
            </button>
          </li>
        ) : (
          <li>
            <Link
              to="/login"
              className={location.pathname === '/login' ? 'nav-link active' : 'nav-link'}
            >
              Admin login
            </Link>
          </li>
        )}
      </ul>
    </nav>
  )
}
