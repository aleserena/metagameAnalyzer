import { describe, it, expect, vi, beforeEach } from 'vitest'
import { getDecks, getMetagame, clearScryfallCache, clearDecks } from './api'

describe('api', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  it('getDecks builds correct query string with card, deck_name, player', async () => {
    const mockFetch = vi.mocked(fetch)
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ decks: [], total: 0, skip: 0, limit: 50 }),
    } as Response)

    await getDecks({
      card: 'Lightning Bolt',
      deck_name: 'Spider',
      player: 'Jeremy',
    })

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/decks'),
      expect.any(Object)
    )
    const url = (mockFetch.mock.calls[0][0] as string)
    expect(url).toContain('card=Lightning+Bolt')
    expect(url).toContain('deck_name=Spider')
    expect(url).toContain('player=Jeremy')
  })

  it('getMetagame includes date params in query', async () => {
    const mockFetch = vi.mocked(fetch)
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        summary: { total_decks: 0, unique_commanders: 0, unique_archetypes: 0 },
        commander_distribution: [],
        top_cards_main: [],
      }),
    } as Response)

    await getMetagame(false, false, '01/01/25', '31/01/25')

    const url = (mockFetch.mock.calls[0][0] as string)
    expect(url).toContain('date_from=01%2F01%2F25')
    expect(url).toContain('date_to=31%2F01%2F25')
  })

  it('throws with server detail when response is not ok', async () => {
    const mockFetch = vi.mocked(fetch)
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      json: async () => ({ detail: 'Deck not found' }),
    } as Response)
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    await expect(getDecks()).rejects.toThrow('Deck not found')
    expect(consoleSpy).toHaveBeenCalledWith(
      expect.stringContaining('[API]'),
      'Deck not found',
      expect.any(Object)
    )
    consoleSpy.mockRestore()
  })

  it('clearScryfallCache calls POST /api/settings/clear-cache', async () => {
    const mockFetch = vi.mocked(fetch)
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ message: 'Scryfall cache cleared' }),
    } as Response)

    const result = await clearScryfallCache()

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/settings/clear-cache'),
      expect.objectContaining({ method: 'POST' })
    )
    expect(result).toEqual({ message: 'Scryfall cache cleared' })
  })

  it('clearDecks calls POST /api/settings/clear-decks', async () => {
    const mockFetch = vi.mocked(fetch)
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ message: 'Decks cleared' }),
    } as Response)

    const result = await clearDecks()

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/settings/clear-decks'),
      expect.objectContaining({ method: 'POST' })
    )
    expect(result).toEqual({ message: 'Decks cleared' })
  })
})
