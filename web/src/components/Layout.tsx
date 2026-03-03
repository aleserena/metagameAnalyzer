import { useEffect, useState } from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import Navbar from './Navbar'
import { GITHUB_REPO } from '../config'
import { fetchWithTimeout } from '../utils'

function checkTableWrapOverflow() {
  document.querySelectorAll('.table-wrap-outer').forEach((outer) => {
    const inner = outer.querySelector('.table-wrap')
    const scrollable = inner && inner.scrollWidth > inner.clientWidth
    outer.classList.toggle('table-wrap-outer--scrollable', !!scrollable)
  })
}

export default function Layout() {
  const location = useLocation()
  const [buildId, setBuildId] = useState<string | null>(null)
  const [dbEnv, setDbEnv] = useState<string | null>(null)

  useEffect(() => {
    fetchWithTimeout('/api/v1/info')
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error('Info fetch failed'))))
      .then((data: { build_id?: string; db_env?: string }) => {
        setBuildId(data.build_id ?? 'unknown')
        setDbEnv(data.db_env ?? 'unknown')
      })
      .catch(() => {
        setBuildId('unknown')
        setDbEnv('unknown')
      })
  }, [])

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
        <Link to="/login" state={{ from: location }}>Admin login</Link>
        {buildId != null && dbEnv != null && (
          <>
            {' · '}
            {buildId} · DB {dbEnv}
          </>
        )}
      </footer>
      <Toaster
        position="top-right"
        containerStyle={{ top: 'var(--navbar-height)' }}
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
