import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import PlayerAnalysisCharts from './PlayerAnalysisCharts'
import type { PlayerAnalysis } from '../../api'

const baseAnalysis: PlayerAnalysis = {
  player: 'Jeremy',
  player_id: 1,
  per_event: [
    {
      deck_id: 1,
      event_id: 100,
      event_name: 'Event A',
      date: '01/01/25',
      rank: '1',
      normalized_rank: '1',
      normalized_rank_num: 1,
      points: 8,
      player_count: 32,
      format_id: 'LE',
      archetype: 'Red Aggro',
      color_identity: ['R'],
      commanders: [],
    },
    {
      deck_id: 2,
      event_id: 101,
      event_name: 'Event B',
      date: '10/02/25',
      rank: '5-8',
      normalized_rank: '5-8',
      normalized_rank_num: 6.5,
      points: 2,
      player_count: 128,
      format_id: 'MO',
      archetype: 'UW Control',
      color_identity: ['W', 'U'],
      commanders: [],
    },
  ],
  leaderboard_history: [
    { date: '01/01/25', rank: 1, total_players: 10 },
    { date: '10/02/25', rank: 3, total_players: 20 },
  ],
  archetype_distribution: [
    { archetype: 'Red Aggro', count: 1, pct: 50 },
    { archetype: 'UW Control', count: 1, pct: 50 },
  ],
  archetype_performance: [
    {
      archetype: 'Red Aggro',
      count: 1,
      avg_finish: 1,
      best_finish: '1',
      top8_pct: 100,
      win_pct: 100,
    },
  ],
  color_distribution: { W: 20, U: 20, B: 0, R: 50, G: 0, C: 0 },
  color_count_distribution: { '0': 0, '1': 1, '2': 1, '3': 0, '4': 0, '5': 0 },
  format_distribution: [
    { format_id: 'LE', count: 1, pct: 50 },
    { format_id: 'MO', count: 1, pct: 50 },
  ],
  commander_distribution: [],
  average_mana_curve: { '1': 4, '2': 6, '3': 2 },
  top_cards: [
    { card: 'Lightning Bolt', deck_count: 2, total_copies: 8 },
  ],
  pet_cards: [
    { card: 'Lightning Bolt', deck_count: 2, total_copies: 8 },
  ],
  field_size_buckets: [
    { bucket: '<32', count: 1, avg_finish: 1, top8_pct: 100 },
    { bucket: '32-100', count: 0, avg_finish: null, top8_pct: 0 },
    { bucket: '100+', count: 1, avg_finish: 6.5, top8_pct: 100 },
  ],
  metagame_comparison: [
    { archetype: 'Red Aggro', player_pct: 50, global_pct: 12 },
  ],
  highlights: {
    best_finish: '1',
    longest_top8_streak: 2,
    biggest_field_win: 32,
    total_events: 2,
    avg_days_between_events: 40,
    first_event_date: '01/01/25',
    last_event_date: '10/02/25',
  },
}

describe('PlayerAnalysisCharts', () => {
  it('renders the Player Analytics heading with highlights and sections', () => {
    render(<PlayerAnalysisCharts analysis={baseAnalysis} />)
    expect(screen.getByRole('heading', { name: 'Player Analytics' })).toBeInTheDocument()
    expect(screen.getByText('Finish per event')).toBeInTheDocument()
    expect(screen.getByText('Cumulative points')).toBeInTheDocument()
    expect(screen.getByText('Archetypes played')).toBeInTheDocument()
    expect(screen.getByText('Formats')).toBeInTheDocument()
    expect(screen.getByText('Archetype performance')).toBeInTheDocument()
    // Highlights tiles
    expect(screen.getByText('Best finish')).toBeInTheDocument()
    expect(screen.getByText('Total events')).toBeInTheDocument()
  })

  it('hides the commander panel when there are no EDH commanders', () => {
    render(<PlayerAnalysisCharts analysis={baseAnalysis} />)
    expect(screen.queryByText('Most-played commanders')).not.toBeInTheDocument()
  })

  it('shows commanders when present', () => {
    const withCmd: PlayerAnalysis = {
      ...baseAnalysis,
      commander_distribution: [
        { commander: 'Atraxa', count: 3, pct: 75 },
        { commander: 'Urza', count: 1, pct: 25 },
      ],
    }
    render(<PlayerAnalysisCharts analysis={withCmd} />)
    expect(screen.getByText('Most-played commanders')).toBeInTheDocument()
  })

  it('returns nothing when the player has no events', () => {
    const empty: PlayerAnalysis = {
      ...baseAnalysis,
      per_event: [],
      leaderboard_history: [],
      archetype_distribution: [],
      archetype_performance: [],
      top_cards: [],
      pet_cards: [],
      metagame_comparison: [],
      field_size_buckets: [],
      format_distribution: [],
      commander_distribution: [],
    }
    const { container } = render(<PlayerAnalysisCharts analysis={empty} />)
    expect(container).toBeEmptyDOMElement()
  })
})
