import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import ChangeLogPanel, { describeActor } from './ChangeLogPanel'
import * as api from '../../api'

vi.mock('../../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api')>()),
  getChangeLog: vi.fn(),
}))

const CHANGES = [
  {
    id: 2,
    at: '2026-11-12T22:10:00Z',
    actor: 'link:event_edit:Store organiser',
    action: 'deck.update',
    event_id: '92583',
    deck_id: 903286,
    summary: 'Edited deck of Ana: rank',
  },
  {
    id: 1,
    at: '2026-11-12T22:00:00Z',
    actor: 'admin',
    action: 'event.delete',
    event_id: 'm4',
    deck_id: null,
    summary: 'Deleted event and its decks',
  },
]

describe('describeActor', () => {
  it('names the admin and links in plain words, never showing a raw key', () => {
    expect(describeActor('admin')).toBe('Admin')
    expect(describeActor('link:event_edit:Store organiser')).toBe('Edit link · Store organiser')
    expect(describeActor('link:deck_upload:unlabelled')).toBe('Upload link')
    expect(describeActor('link:feedback:Round 3: table 2')).toBe('Feedback link · Round 3: table 2')
    expect(describeActor('link:unknown')).toBe('Link')
    expect(describeActor('')).toBe('Unknown')
  })
})

describe('ChangeLogPanel', () => {
  beforeEach(() => {
    vi.mocked(api.getChangeLog).mockReset().mockResolvedValue({ changes: CHANGES })
  })

  it('lists changes with who made them', async () => {
    render(<ChangeLogPanel />)

    expect(await screen.findByText('Edited deck of Ana: rank')).toBeInTheDocument()
    expect(screen.getByText('Edit link · Store organiser')).toBeInTheDocument()
    expect(screen.getByText('Admin')).toBeInTheDocument()
    expect(api.getChangeLog).toHaveBeenCalledWith(undefined)
  })

  it('filters by event id', async () => {
    render(<ChangeLogPanel />)
    await screen.findByText('Deleted event and its decks')

    fireEvent.change(screen.getByLabelText('Event ID'), { target: { value: ' 92583 ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Show' }))

    await waitFor(() => expect(api.getChangeLog).toHaveBeenLastCalledWith('92583'))
  })

  it('says so when nothing is recorded', async () => {
    vi.mocked(api.getChangeLog).mockResolvedValue({ changes: [] })
    render(<ChangeLogPanel />)

    expect(await screen.findByText('No changes recorded yet.')).toBeInTheDocument()
  })
})
