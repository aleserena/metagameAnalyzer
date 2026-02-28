import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import FiltersPanel from './FiltersPanel'

describe('FiltersPanel', () => {
  it('renders title and children', () => {
    render(
      <FiltersPanel title="Date & events">
        <button type="button">Apply</button>
      </FiltersPanel>
    )
    expect(screen.getByText('Date & events')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Apply' })).toBeInTheDocument()
  })

  it('defaults title to "Filters"', () => {
    render(<FiltersPanel><span>Content</span></FiltersPanel>)
    expect(screen.getByText('Filters')).toBeInTheDocument()
    expect(screen.getByText('Content')).toBeInTheDocument()
  })
})
