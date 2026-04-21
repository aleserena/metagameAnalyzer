import { Suspense, lazy, type ReactElement } from 'react'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import Layout from './components/Layout'
import ErrorBoundary from './components/ErrorBoundary'
import AdminGuard from './components/AdminGuard'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Events = lazy(() => import('./pages/Events'))
const EventDetail = lazy(() => import('./pages/EventDetail'))
const Metagame = lazy(() => import('./pages/Metagame'))
const Decks = lazy(() => import('./pages/Decks'))
const DeckDetail = lazy(() => import('./pages/DeckDetail'))
const DeckCompare = lazy(() => import('./pages/DeckCompare'))
const Archetypes = lazy(() => import('./pages/Archetypes'))
const ArchetypeDetail = lazy(() => import('./pages/ArchetypeDetail'))
const Matchups = lazy(() => import('./pages/Matchups'))
const Players = lazy(() => import('./pages/Players'))
const PlayerDetail = lazy(() => import('./pages/PlayerDetail'))
const Scrape = lazy(() => import('./pages/Scrape'))
const Settings = lazy(() => import('./pages/Settings'))
const Login = lazy(() => import('./pages/Login'))
const UploadDeck = lazy(() => import('./pages/UploadDeck'))
const Feedback = lazy(() => import('./pages/Feedback'))

function routeElement(element: ReactElement) {
  return <Suspense fallback={<div className="loading">Loading...</div>}>{element}</Suspense>
}

const router = createBrowserRouter(
  [
    {
      path: '/upload/:token',
      element: (
        <ErrorBoundary>
          {routeElement(<UploadDeck />)}
        </ErrorBoundary>
      ),
    },
    {
      path: '/',
      element: (
        <ErrorBoundary>
          {routeElement(<Layout />)}
        </ErrorBoundary>
      ),
      children: [
        { index: true, element: routeElement(<Dashboard />) },
        { path: 'login', element: routeElement(<Login />) },
        { path: 'events', element: routeElement(<Events />) },
        { path: 'events/:eventId', element: routeElement(<EventDetail />) },
        { path: 'metagame', element: routeElement(<Metagame />) },
        { path: 'archetypes', element: routeElement(<Archetypes />) },
        { path: 'archetypes/:archetypeName', element: routeElement(<ArchetypeDetail />) },
        { path: 'matchups', element: routeElement(<Matchups />) },
        { path: 'decks', element: routeElement(<Decks />) },
        { path: 'decks/compare', element: routeElement(<DeckCompare />) },
        { path: 'decks/:deckId', element: routeElement(<DeckDetail />) },
        { path: 'players', element: routeElement(<Players />) },
        { path: 'players/:playerId', element: routeElement(<PlayerDetail />) },
        { path: 'feedback', element: routeElement(<Feedback />) },
        {
          path: 'scrape',
          element: routeElement(
            <AdminGuard>
              <Scrape />
            </AdminGuard>
          ),
        },
        {
          path: 'settings',
          element: routeElement(
            <AdminGuard>
              <Settings />
            </AdminGuard>
          ),
        },
      ],
    },
  ],
  {
    future: {
      v7_relativeSplatPath: true,
    },
  }
)

export default function App() {
  return (
    <RouterProvider
      router={router}
      future={{ v7_startTransition: true }}
    />
  )
}
