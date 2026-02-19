import type { Deck, MetagameReport, Event, PlayerStats, SimilarDeck } from './types'

const API_BASE = '/api'

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

export async function getDecks(params?: {
  event_id?: number
  event_ids?: string
  commander?: string
  deck_name?: string
  archetype?: string
  player?: string
  card?: string
  sort?: string
  order?: string
  skip?: number
  limit?: number
}): Promise<{ decks: Deck[]; total: number; skip: number; limit: number }> {
  const search = new URLSearchParams()
  if (params?.event_id != null) search.set('event_id', String(params.event_id))
  if (params?.event_ids) search.set('event_ids', params.event_ids)
  if (params?.commander) search.set('commander', params.commander)
  if (params?.deck_name) search.set('deck_name', params.deck_name)
  if (params?.archetype) search.set('archetype', params.archetype)
  if (params?.player) search.set('player', params.player)
  if (params?.card) search.set('card', params.card)
  if (params?.sort) search.set('sort', params.sort)
  if (params?.order) search.set('order', params.order)
  if (params?.skip != null) search.set('skip', String(params.skip))
  if (params?.limit != null) search.set('limit', String(params.limit))
  const q = search.toString()
  return fetchApi(`/decks${q ? `?${q}` : ''}`)
}

export async function getDeck(deckId: number): Promise<Deck> {
  return fetchApi(`/decks/${deckId}`)
}

export async function getDeckCompare(deckIds: number[]): Promise<{ decks: Deck[] }> {
  return fetchApi(`/decks/compare?ids=${deckIds.join(',')}`)
}

export async function getSimilarDecks(
  deckId: number,
  limit = 10,
  eventIds?: string
): Promise<{ similar: SimilarDeck[] }> {
  const params = new URLSearchParams()
  params.set('limit', String(limit))
  if (eventIds) params.set('event_ids', eventIds)
  return fetchApi(`/decks/${deckId}/similar?${params.toString()}`)
}

export async function getDuplicateDecks(eventIds?: string): Promise<{
  duplicates: Array<{
    primary_deck_id: number
    primary_name: string
    primary_player: string
    primary_event: string
    primary_date: string
    duplicate_deck_ids: number[]
    duplicates: Array<{ deck_id: number; name: string; player: string; event_name: string; date: string }>
  }>
}> {
  const params = eventIds ? `?event_ids=${encodeURIComponent(eventIds)}` : ''
  return fetchApi(`/decks/duplicates${params}`)
}

export interface CardLookupResult {
  name?: string
  image_uris?: { small?: string; normal?: string; large?: string }
  mana_cost?: string
  cmc?: number
  type_line?: string
  colors?: string[]
  color_identity?: string[]
  error?: string
}

export async function getCardLookup(names: string[]): Promise<Record<string, CardLookupResult>> {
  if (names.length === 0) return {}
  return fetchApi('/cards/lookup', {
    method: 'POST',
    body: JSON.stringify({ names }),
  })
}

export interface CardMeta {
  mana_cost: string
  cmc: number
  type_line: string
  colors: string[]
}

export interface DeckAnalysis {
  mana_curve: Record<number, number>
  color_distribution: Record<string, number>
  lands_distribution: { lands: number; nonlands: number }
  type_distribution?: Record<string, number>
  grouped_by_type?: Record<string, [number, string][]>
  grouped_by_type_sideboard?: Record<string, [number, string][]>
  grouped_by_cmc?: Record<string, [number, string][]>
  grouped_by_cmc_sideboard?: Record<string, [number, string][]>
  grouped_by_color?: Record<string, [number, string][]>
  grouped_by_color_sideboard?: Record<string, [number, string][]>
  card_meta?: Record<string, CardMeta>
}

export async function getDeckAnalysis(deckId: number): Promise<DeckAnalysis> {
  return fetchApi(`/decks/${deckId}/analysis`)
}

export async function getEvents(): Promise<{ events: Event[] }> {
  return fetchApi('/events')
}

export async function getDateRange(): Promise<{ min_date: string | null; max_date: string | null; last_event_date: string | null }> {
  return fetchApi('/date-range')
}

export async function getFormatInfo(): Promise<{ format_id: string | null; format_name: string | null }> {
  return fetchApi('/format-info')
}

export async function getMetagame(
  placementWeighted = false,
  ignoreLands = false,
  dateFrom?: string | null,
  dateTo?: string | null,
  eventId?: number | null,
  eventIds?: string | null
): Promise<MetagameReport> {
  const params = new URLSearchParams()
  params.set('placement_weighted', String(placementWeighted))
  params.set('ignore_lands', String(ignoreLands))
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  if (eventIds) params.set('event_ids', eventIds)
  else if (eventId != null) params.set('event_id', String(eventId))
  return fetchApi(`/metagame?${params.toString()}`)
}

export async function getPlayers(dateFrom?: string | null, dateTo?: string | null): Promise<{ players: PlayerStats[] }> {
  const params = new URLSearchParams()
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  const q = params.toString()
  return fetchApi(`/players${q ? `?${q}` : ''}`)
}

export interface PlayerDetail {
  player: string
  wins: number
  top2: number
  top4: number
  top8: number
  points: number
  deck_count: number
  decks: { deck_id: number; name: string; event_name: string; date: string; rank: string }[]
}

export async function getPlayerDetail(playerName: string): Promise<PlayerDetail> {
  return fetchApi(`/players/${encodeURIComponent(playerName)}`)
}

export async function getPlayerAliases(): Promise<{ aliases: Record<string, string> }> {
  return fetchApi('/player-aliases')
}

export async function addPlayerAlias(alias: string, canonical: string): Promise<{ aliases: Record<string, string> }> {
  return fetchApi('/player-aliases', {
    method: 'POST',
    body: JSON.stringify({ alias, canonical }),
  })
}

export async function removePlayerAlias(alias: string): Promise<{ aliases: Record<string, string> }> {
  return fetchApi(`/player-aliases/${encodeURIComponent(alias)}`, { method: 'DELETE' })
}

export async function getSimilarPlayers(name: string, limit = 10): Promise<{ similar: string[] }> {
  return fetchApi(`/players/similar?name=${encodeURIComponent(name)}&limit=${limit}`)
}

export async function loadDecks(file: File): Promise<{ loaded: number; message: string }> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API_BASE}/load`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

export async function loadDecksFromPath(path: string): Promise<{ loaded: number; message: string }> {
  return fetchApi('/load', {
    method: 'POST',
    body: JSON.stringify({ path }),
  })
}

export async function runScrape(params: {
  format?: string
  period?: string
  store?: string
  event_ids?: string
}): Promise<{ loaded: number; message: string; progress: string[] }> {
  return fetchApi('/scrape', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}
