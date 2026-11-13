import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import SnapshotsPanel from './SnapshotsPanel'
import * as api from '../../api'

vi.mock('../../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api')>()),
  getSnapshots: vi.fn(),
  restoreSnapshot: vi.fn(),
}))

const SNAPSHOTS = [
  {
    id: 12,
    event_id: '92583',
    event_name: 'Liga Hadouken',
    created_at: '2026-11-12T22:00:00Z',
    reason: 'delete',
    deck_count: 26,
    matchup_count: 130,
  },
  {
    id: 9,
    event_id: 'm4',
    event_name: 'Store Showdown',
    created_at: '2026-11-10T18:30:00Z',
    reason: 'rescrape',
    deck_count: 8,
    matchup_count: 0,
  },
]

describe('SnapshotsPanel', () => {
  beforeEach(() => {
    vi.mocked(api.getSnapshots).mockReset().mockResolvedValue({ snapshots: SNAPSHOTS })
    vi.mocked(api.restoreSnapshot).mockReset().mockResolvedValue({
      event_id: '92583',
      deck_count: 26,
      matchup_count: 130,
      safety_snapshot_id: 13,
      also_saved_event_ids: [],
    })
  })

  it('lists snapshots with a plain-language reason', async () => {
    render(<SnapshotsPanel />)

    expect(await screen.findByText('Liga Hadouken')).toBeInTheDocument()
    expect(screen.getByText('Store Showdown')).toBeInTheDocument()
    expect(screen.getByText('Before delete')).toBeInTheDocument()
    expect(screen.getByText('Before re-scrape')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Restore' })).toHaveLength(2)
  })

  it('asks before restoring and names the event', async () => {
    render(<SnapshotsPanel />)
    fireEvent.click((await screen.findAllByRole('button', { name: 'Restore' }))[0])

    const question = screen.getByRole('alertdialog')
    expect(question).toHaveTextContent('Restore "Liga Hadouken" to how it was on')
    expect(question).toHaveTextContent('The current version is saved first, so this can be undone.')
    expect(api.restoreSnapshot).not.toHaveBeenCalled()
  })

  it('restores on confirm, reports success and reloads the list', async () => {
    render(<SnapshotsPanel />)
    fireEvent.click((await screen.findAllByRole('button', { name: 'Restore' }))[0])
    fireEvent.click(screen.getByRole('button', { name: 'Restore event' }))

    await waitFor(() => expect(api.restoreSnapshot).toHaveBeenCalledWith(12))
    expect(await screen.findByText('Event restored.')).toBeInTheDocument()
    expect(api.getSnapshots).toHaveBeenCalledTimes(2)
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it('does nothing when the restore is cancelled', async () => {
    render(<SnapshotsPanel />)
    fireEvent.click((await screen.findAllByRole('button', { name: 'Restore' }))[0])
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(api.restoreSnapshot).not.toHaveBeenCalled()
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it('shows the error and keeps the list when a restore fails', async () => {
    vi.mocked(api.restoreSnapshot).mockRejectedValue(new Error('Failed to restore the snapshot. Nothing was changed.'))
    render(<SnapshotsPanel />)
    fireEvent.click((await screen.findAllByRole('button', { name: 'Restore' }))[0])
    fireEvent.click(screen.getByRole('button', { name: 'Restore event' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Failed to restore the snapshot. Nothing was changed.')
    expect(screen.getByText('Liga Hadouken')).toBeInTheDocument()
  })

  it('says so when there are no snapshots yet', async () => {
    vi.mocked(api.getSnapshots).mockResolvedValue({ snapshots: [] })
    render(<SnapshotsPanel />)

    expect(await screen.findByText(/No snapshots yet/)).toBeInTheDocument()
  })

  it('searches by event name or id, so older snapshots stay reachable', async () => {
    render(<SnapshotsPanel />)
    await screen.findByText('Liga Hadouken')
    expect(api.getSnapshots).toHaveBeenLastCalledWith(undefined)

    fireEvent.change(screen.getByLabelText('Event name or ID'), { target: { value: ' hadouken ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))

    await waitFor(() => expect(api.getSnapshots).toHaveBeenLastCalledWith('hadouken'))
  })

  it('says which other events were saved before a restore touched them', async () => {
    vi.mocked(api.restoreSnapshot).mockResolvedValue({
      event_id: '92583',
      deck_count: 26,
      matchup_count: 130,
      safety_snapshot_id: null,
      also_saved_event_ids: ['m7'],
    })
    render(<SnapshotsPanel />)
    fireEvent.click((await screen.findAllByRole('button', { name: 'Restore' }))[0])
    fireEvent.click(screen.getByRole('button', { name: 'Restore event' }))

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Event restored. Its decks were taken back from event m7, which was saved first.'
    )
  })
})
