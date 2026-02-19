import { Navigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function AdminGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return null
  if (user !== 'admin') return <Navigate to="/login" replace />
  return <>{children}</>
}
