import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import Layout from './components/Layout'
import ErrorBoundary from './components/ErrorBoundary'
import AdminGuard from './components/AdminGuard'
import Dashboard from './pages/Dashboard'
import Events from './pages/Events'
import EventDetail from './pages/EventDetail'
import Metagame from './pages/Metagame'
import Decks from './pages/Decks'
import DeckDetail from './pages/DeckDetail'
import DeckCompare from './pages/DeckCompare'
import Archetypes from './pages/Archetypes'
import ArchetypeDetail from './pages/ArchetypeDetail'
import Players from './pages/Players'
import PlayerDetail from './pages/PlayerDetail'
import Scrape from './pages/Scrape'
import Settings from './pages/Settings'
import Login from './pages/Login'
import UploadDeck from './pages/UploadDeck'
import Feedback from './pages/Feedback'

const router = createBrowserRouter(
  [
    { path: '/login', element: <Login /> },
    { path: '/upload/:token', element: <UploadDeck /> },
    {
      path: '/',
      element: (
        <ErrorBoundary>
          <Layout />
        </ErrorBoundary>
      ),
      children: [
        { index: true, element: <Dashboard /> },
        { path: 'events', element: <Events /> },
        { path: 'events/:eventId', element: <EventDetail /> },
        { path: 'metagame', element: <Metagame /> },
        { path: 'archetypes', element: <Archetypes /> },
        { path: 'archetypes/:archetypeName', element: <ArchetypeDetail /> },
        { path: 'decks', element: <Decks /> },
        { path: 'decks/compare', element: <DeckCompare /> },
        { path: 'decks/:deckId', element: <DeckDetail /> },
        { path: 'players', element: <Players /> },
        { path: 'players/:playerName', element: <PlayerDetail /> },
        { path: 'feedback', element: <Feedback /> },
        {
          path: 'scrape',
          element: (
            <AdminGuard>
              <Scrape />
            </AdminGuard>
          ),
        },
        {
          path: 'settings',
          element: (
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
