import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { AuthProvider } from './contexts/AuthContext'
import App from './App'
import './style.css'

createRoot(document.getElementById('app')!).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>
)
