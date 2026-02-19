import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Metagame from './pages/Metagame'
import Decks from './pages/Decks'
import DeckDetail from './pages/DeckDetail'
import DeckCompare from './pages/DeckCompare'
import Players from './pages/Players'
import PlayerDetail from './pages/PlayerDetail'
import Scrape from './pages/Scrape'

const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'metagame', element: <Metagame /> },
      { path: 'decks', element: <Decks /> },
      { path: 'decks/compare', element: <DeckCompare /> },
      { path: 'decks/:deckId', element: <DeckDetail /> },
      { path: 'players', element: <Players /> },
      { path: 'players/:playerName', element: <PlayerDetail /> },
      { path: 'scrape', element: <Scrape /> },
    ],
  },
])

export default function App() {
  return <RouterProvider router={router} />
}
