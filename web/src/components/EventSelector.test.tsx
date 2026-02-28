import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import EventSelector from './EventSelector'

const mockEvents = [
  { event_id: 1, event_name: 'Event One', date: '01/01/26', format_id: 'EDH' },
  { event_id: 2, event_name: 'Event Two', date: '15/02/26', format_id: 'EDH' },
]

describe('EventSelector', () => {
  it('renders label and event options when opened', () => {
    const onChange = vi.fn()
    render(
      <EventSelector events={mockEvents} selectedIds={[]} onChange={onChange} />
    )
    expect(screen.getByText('Events')).toBeInTheDocument()
    const button = screen.getByRole('button', { name: /select events/i })
    fireEvent.click(button)
    expect(screen.getByText(/Event One/)).toBeInTheDocument()
    expect(screen.getByText(/Event Two/)).toBeInTheDocument()
  })

  it('calls onChange when an event is toggled', () => {
    const onChange = vi.fn()
    render(
      <EventSelector events={mockEvents} selectedIds={[]} onChange={onChange} />
    )
    fireEvent.click(screen.getByRole('button', { name: /select events/i }))
    fireEvent.click(screen.getByText(/Event One/))
    expect(onChange).toHaveBeenCalledWith([1])
  })
})
