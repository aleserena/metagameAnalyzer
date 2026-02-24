import { useEffect } from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import Navbar from './Navbar'
import { GITHUB_REPO } from '../config'

function checkTableWrapOverflow() {
  document.querySelectorAll('.table-wrap-outer').forEach((outer) => {
    const inner = outer.querySelector('.table-wrap')
    const scrollable = inner && inner.scrollWidth > inner.clientWidth
    outer.classList.toggle('table-wrap-outer--scrollable', !!scrollable)
  })
}

export default function Layout() {
  const location = useLocation()

  useEffect(() => {
    const runCheck = () => checkTableWrapOverflow()
    runCheck()
    const t = setTimeout(runCheck, 150)
    window.addEventListener('resize', runCheck)
    const main = document.querySelector('main.main')
    const resizeObserver = main ? new ResizeObserver(runCheck) : null
    if (main && resizeObserver) resizeObserver.observe(main)
    return () => {
      clearTimeout(t)
      window.removeEventListener('resize', runCheck)
      resizeObserver?.disconnect()
    }
  }, [location.pathname])

  useEffect(() => {
    const observer = new MutationObserver(() => {
      requestAnimationFrame(checkTableWrapOverflow)
    })
    observer.observe(document.body, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [])

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
        {' · '}
        <Link to="/feedback">Feedback</Link>
        {' · '}
        <Link to="/login">Admin login</Link>
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
