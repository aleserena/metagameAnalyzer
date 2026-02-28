import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import DeckAnalysisCharts from './DeckAnalysisCharts'
import type { DeckAnalysis } from '../../api'

const mockAnalysis: DeckAnalysis = {
  mana_curve: { 0: 5, 1: 10, 2: 12, 3: 8, 4: 4 },
  mana_curve_permanent: {},
  mana_curve_non_permanent: {},
  color_distribution: { W: 10, U: 15, B: 0, R: 20, G: 12, C: 5 },
  lands_distribution: { lands: 38, nonlands: 62 },
  type_distribution: { Creature: 25, Land: 38, Instant: 10 },
  grouped_by_type: {},
  grouped_by_cmc: {},
  grouped_by_color: {},
  grouped_by_type_sideboard: {},
  grouped_by_cmc_sideboard: {},
  grouped_by_color_sideboard: {},
}

describe('DeckAnalysisCharts', () => {
  it('renders Deck Analysis heading and chart sections', () => {
    render(<DeckAnalysisCharts analysis={mockAnalysis} />)
    expect(screen.getByRole('heading', { name: 'Deck Analysis' })).toBeInTheDocument()
    expect(screen.getByText('Mana Curve')).toBeInTheDocument()
    expect(screen.getByText('Color Distribution')).toBeInTheDocument()
  })
})
