import { Link, useLocation } from 'react-router-dom'

const navItems = [
  { path: '/', label: 'Dashboard' },
  { path: '/metagame', label: 'Metagame' },
  { path: '/decks', label: 'Decks' },
  { path: '/decks/compare', label: 'Compare' },
  { path: '/players', label: 'Players' },
  { path: '/scrape', label: 'Scrape' },
]

export default function Navbar() {
  const location = useLocation()

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
      </ul>
    </nav>
  )
}
