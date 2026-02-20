import { Outlet } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import Navbar from './Navbar'
import { GITHUB_REPO } from '../config'

export default function Layout() {
  return (
    <div className="layout">
      <Navbar />
      <main className="main">
        <Outlet />
      </main>
      <footer className="app-footer">
        Vibe-coded with love &lt;3 by Alejandro Serena
        {' · '}
        <a href={GITHUB_REPO} target="_blank" rel="noopener noreferrer">GitHub</a>
      </footer>
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 4000,
          style: {
            background: 'var(--bg-card)',
            color: 'var(--text)',
            border: '1px solid var(--border)',
          },
        }}
      />
    </div>
  )
}
