import type { Deck, MetagameReport, Event, PlayerStats, SimilarDeck, ArchetypeDetail } from './types'
import { getToken } from './contexts/AuthContext'
import { fetchWithTimeout } from './utils'

const API_BASE = '/api'
const EVENT_EDIT_TOKEN_KEY = 'event_edit_token'

function getAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  const eventEditToken = typeof sessionStorage !== 'undefined' ? sessionStorage.getItem(EVENT_EDIT_TOKEN_KEY) : null
  if (eventEditToken) headers['X-Event-Edit-Token'] = eventEditToken
  return headers
}

export function getEventEditToken(): string | null {
  return typeof sessionStorage !== 'undefined' ? sessionStorage.getItem(EVENT_EDIT_TOKEN_KEY) : null
}

export function setEventEditToken(token: string): void {
  sessionStorage.setItem(EVENT_EDIT_TOKEN_KEY, token)
}

export function clearEventEditToken(): void {
  sessionStorage.removeItem(EVENT_EDIT_TOKEN_KEY)
}

/** Shared 401 + error handling for fetch. Use for JSON or blob responses with auth. */
async function fetchWithAuth(
  path: string,
  options: RequestInit = {},
  responseType: 'json' | 'blob' = 'json'
): Promise<unknown> {
  const headers: Record<string, string> = { ...getAuthHeaders() }
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }
  const res = await fetchWithTimeout(`${API_BASE}${path}`, {
    ...options,
    headers: { ...headers, ...(options.headers as Record<string, string>) },
  })
  if (res.status === 401) {
    localStorage.removeItem('admin_token')
    window.dispatchEvent(new Event('auth-logout'))
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = err.detail ?? res.statusText
    const message = typeof detail === 'string' ? detail : JSON.stringify(detail)
    console.error('[API]', res.status, path, detail, err)
    throw new Error(message)
  }
  return responseType === 'blob' ? res.blob() : res.json()
}

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetchWithTimeout(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
      ...options?.headers,
    },
  })
  if (res.status === 401) {
    localStorage.removeItem('admin_token')
    window.dispatchEvent(new Event('auth-logout'))
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = err.detail ?? res.statusText
    const message = typeof detail === 'string' ? detail : JSON.stringify(detail)
    console.error(`[API] ${res.status} ${path}`, detail, err)
    throw new Error(message)
  }
  return res.json()
}

export async function submitFeedback(body: {
  type: string
  title: string
  description: string
  email?: string | null
  website?: string | null
  captcha_a: number
  captcha_b: number
  captcha_answer: number
}): Promise<{ url: string; number?: number }> {
  const res = await fetchWithTimeout(`${API_BASE}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = err.detail ?? res.statusText
    const message = typeof detail === 'string' ? detail : JSON.stringify(detail)
    throw new Error(message)
  }
  return res.json()
}

export async function getDecks(params?: {
  event_id?: number | string
  event_ids?: string
  commander?: string
  deck_name?: string
  archetype?: string
  player?: string
  card?: string
  /** Commander-based color identity filter, e.g. "W,U" for Azorius. */
  colors?: string
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
  if (params?.colors) search.set('colors', params.colors)
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

export interface CardFaceLookup {
  name: string
  image_uris?: { small?: string; normal?: string; large?: string }
}

export interface CardLookupResult {
  name?: string
  image_uris?: { small?: string; normal?: string; large?: string }
  mana_cost?: string
  cmc?: number
  type_line?: string
  colors?: string[]
  color_identity?: string[]
  /** Both faces for double-faced cards (name + image per face). */
  card_faces?: CardFaceLookup[]
  error?: string
}

export async function getCardLookup(names: string[]): Promise<Record<string, CardLookupResult>> {
  if (names.length === 0) return {}
  return fetchApi('/cards/lookup', {
    method: 'POST',
    body: JSON.stringify({ names }),
  })
}

export async function getCardSearch(query: string): Promise<{ data: string[] }> {
  const q = encodeURIComponent(query.trim())
  return fetchApi(`/cards/search?q=${q}`)
}

export interface CardMeta {
  mana_cost: string
  cmc: number
  type_line: string
  colors: string[]
}

export interface DeckAnalysis {
  mana_curve: Record<number, number>
  mana_curve_permanent?: Record<number, number>
  mana_curve_non_permanent?: Record<number, number>
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

export type EventWithOrigin = Event

export async function getEvents(): Promise<{ events: EventWithOrigin[] }> {
  return fetchApi('/events')
}

/** Admin only. Returns event_ids that have at least one matchup discrepancy. */
export async function getEventIdsWithDiscrepancies(): Promise<{ event_ids: string[] }> {
  return fetchApi('/events/event-ids-with-discrepancies')
}

export async function getEvent(eventId: number | string): Promise<EventWithOrigin & { player_count?: number }> {
  return fetchApi(`/events/${encodeURIComponent(String(eventId))}`)
}

export async function createEvent(body: {
  event_name: string
  date: string
  format_id: string
  player_count?: number
  event_id?: number | string
  store?: string
  location?: string
}): Promise<{ event_id: string; event_name: string; store: string; location: string; date: string; format_id: string; player_count: number }> {
  return fetchApi('/events', { method: 'POST', body: JSON.stringify(body) })
}

export async function updateEvent(
  eventId: number | string,
  params: { event_name?: string; date?: string; format_id?: string; player_count?: number; store?: string; location?: string }
): Promise<{ event_id: string; message: string }> {
  const search = new URLSearchParams()
  if (params.event_name != null) search.set('event_name', params.event_name)
  if (params.date != null) search.set('date', params.date)
  if (params.format_id != null) search.set('format_id', params.format_id)
  if (params.player_count != null) search.set('player_count', String(params.player_count))
  if (params.store != null) search.set('store', params.store)
  if (params.location != null) search.set('location', params.location)
  const q = search.toString()
  return fetchApi(`/events/${encodeURIComponent(String(eventId))}${q ? `?${q}` : ''}`, { method: 'PUT' })
}

export async function deleteEvent(eventId: number | string): Promise<{ event_id: string; message: string }> {
  return fetchApi(`/events/${encodeURIComponent(String(eventId))}`, { method: 'DELETE' })
}

/** Admin only. Preview merging two events. Cannot merge two MTGTop8 events. */
export interface MergeConflictItem {
  field: string
  value_keep: string | number | unknown[] | null | unknown
  value_remove: string | number | unknown[] | null | unknown
}

export interface DeckPairPreview {
  deck_keep: Deck
  deck_remove: Deck
  conflicts: MergeConflictItem[]
}

export interface MergePreviewResponse {
  can_merge: boolean
  error?: string
  event_a: Event
  event_b: Event
  conflicts: MergeConflictItem[]
  merged_preview: Event
  keep_event_id: string
  remove_event_id: string
  deck_pairs: DeckPairPreview[]
  decks_keep_only: Deck[]
  decks_remove_only: Deck[]
}

export async function getMergePreview(eventIdA: string, eventIdB: string): Promise<MergePreviewResponse> {
  const params = new URLSearchParams({ event_id_a: eventIdA, event_id_b: eventIdB })
  return fetchApi(`/events/merge-preview?${params.toString()}`)
}

/** Admin only. Merge two events (players/decks merged when same or manually paired; unpaired decks moved). */
export interface PlayerMergePair {
  deck_id_keep: number
  deck_id_remove: number
}

export async function mergeEvents(body: {
  event_id_keep: string
  event_id_remove: string
  resolutions?: Record<string, 'keep' | 'remove'>
  player_merges?: PlayerMergePair[]
  deck_resolutions?: Record<string, Record<string, 'keep' | 'remove'>>
}): Promise<{ message: string; keep_event_id: string; remove_event_id: string; decks_merged: number; decks_moved: number }> {
  return fetchApi('/events/merge', { method: 'POST', body: JSON.stringify(body) })
}

export async function addDeckToEvent(
  eventId: number | string
): Promise<{ event_id: string; deck_id: number; message: string }> {
  return fetchApi(`/events/${encodeURIComponent(String(eventId))}/decks/add`, { method: 'POST' })
}

export async function createEventUploadLinks(
  eventId: number | string,
  options?: { count?: number; expires_in_days?: number; deck_id?: number; type?: 'event_edit' | 'feedback' }
): Promise<{
  links: Array<{ token: string; url: string; expires_at: string | null; deck_id?: number }>
}> {
  return fetchApi(`/events/${encodeURIComponent(String(eventId))}/upload-links`, {
    method: 'POST',
    body: JSON.stringify({
      count: options?.deck_id != null && options?.type !== 'feedback' ? undefined : (options?.count ?? 1),
      expires_in_days: options?.expires_in_days ?? undefined,
      deck_id: options?.deck_id ?? undefined,
      type: options?.type ?? undefined,
    }),
  })
}

export async function putPlayerEmail(player: string, email: string): Promise<{ ok: boolean }> {
  return fetchApi('/player-emails', { method: 'PUT', body: JSON.stringify({ player, email }) })
}

export async function sendMissingDeckLinks(eventId: string): Promise<{ sent: number; failed: string[] }> {
  return fetchApi(`/events/${encodeURIComponent(eventId)}/send-missing-deck-links`, { method: 'POST' })
}

/** Email one-time deck upload links for all of this player's missing decks. Requires player to have email set. */
export async function sendPlayerMissingDeckLinks(playerName: string): Promise<{ sent: number; message?: string }> {
  return fetchApi(`/players/${encodeURIComponent(playerName)}/send-missing-deck-links`, { method: 'POST' })
}

export async function sendFeedbackLinks(eventId: string): Promise<{ sent: number }> {
  return fetchApi(`/events/${encodeURIComponent(eventId)}/send-feedback-links`, { method: 'POST' })
}

/** Send one feedback link by email to a single player for this event. Invalidates any previous feedback link for that player's deck. */
export async function sendFeedbackLinkToPlayer(eventId: string, player: string): Promise<{ sent: number }> {
  return fetchApi(`/events/${encodeURIComponent(eventId)}/send-feedback-link-to-player`, {
    method: 'POST',
    body: JSON.stringify({ player }),
  })
}

export async function getMatchupDiscrepancies(eventId: string): Promise<{
  discrepancies: Array<{
    deck_id_a: number
    deck_id_b: number
    player_a: string
    player_b: string
    matchup_a: { id: number; result: string; result_note?: string; round?: number }
    matchup_b: { id: number; result: string; result_note?: string; round?: number }
    result_a: string
    result_b: string
  }>
}> {
  return fetchApi(`/events/${encodeURIComponent(eventId)}/matchup-discrepancies`)
}

export async function patchMatchup(
  matchupId: number,
  body: { result?: string; result_note?: string; round?: number }
): Promise<{ ok: boolean }> {
  return fetchApi(`/matchups/${matchupId}`, { method: 'PATCH', body: JSON.stringify(body) })
}

export async function getMatchupsSummary(params?: {
  format_id?: string
  event_ids?: string
  from_date?: string
  to_date?: string
  archetype?: string[]
}): Promise<{
  list: Array<{
    archetype: string
    opponent_archetype: string
    wins: number
    losses: number
    draws: number
    intentional_draws: number
    matches: number
    win_rate: number
  }>
  archetypes: string[]
  matrix: (number | null)[][]
  min_matches: number
}> {
  const search = new URLSearchParams()
  if (params?.format_id) search.set('format_id', params.format_id)
  if (params?.event_ids) search.set('event_ids', params.event_ids)
  if (params?.from_date) search.set('from_date', params.from_date)
  if (params?.to_date) search.set('to_date', params.to_date)
  if (params?.archetype?.length) params.archetype.forEach((a) => search.append('archetype', a))
  const q = search.toString()
  return fetchApi(`/matchups/summary${q ? `?${q}` : ''}`)
}

export async function getMatchupsMinMatchesSetting(): Promise<{ value: number }> {
  return fetchApi('/settings/matchups-min-matches')
}

export async function putMatchupsMinMatchesSetting(value: number): Promise<{ value: number }> {
  return fetchApi('/settings/matchups-min-matches', {
    method: 'PUT',
    body: JSON.stringify({ value }),
  })
}

/** Create a one-time event edit link (admin-only). Returns URL to event page with ?token= for editing event + decks (no delete event, no new links). */
export async function createEventEditLink(eventId: string): Promise<{
  links: Array<{ token: string; url: string; expires_at: string | null }>
}> {
  return fetchApi(`/events/${encodeURIComponent(eventId)}/upload-links`, {
    method: 'POST',
    body: JSON.stringify({ type: 'event_edit' }),
  })
}

/** Validate one-time event-edit token and return event_id. Public. Marks link as used. */
export async function getEventEditLinkInfo(token: string): Promise<{ event_id: string }> {
  return fetchApiPublic(`/event-edit/${encodeURIComponent(token)}`)
}

/** Public API (no auth) for upload link pages. */
async function fetchApiPublic<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetchWithTimeout(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = err.detail ?? res.statusText
    const message = typeof detail === 'string' ? detail : JSON.stringify(detail)
    throw new Error(message)
  }
  return res.json()
}

export type UploadLinkDeck = {
  deck_id: number
  name: string
  player: string
  rank: string
  mainboard: { qty: number; card: string }[]
  sideboard: { qty: number; card: string }[]
  commanders: string[]
}

export type UploadLinkDeckWithArchetype = UploadLinkDeck & { archetype?: string | null }

export async function getUploadLinkInfo(token: string): Promise<{
  event_id: string
  event_name: string
  format_id: string
  date: string
  mode: 'create' | 'update'
  purpose: 'deck' | 'feedback'
  deck_id?: number
  deck?: UploadLinkDeckWithArchetype | null
}> {
  return fetchApiPublic(`/upload/${encodeURIComponent(token)}`)
}

export async function submitFeedbackWithUploadLink(
  token: string,
  body: {
    archetype: string
    deck_name?: string
    rank?: string
    matchups: Array<{ opponent_player: string; result: string; result_note?: string; round?: number }>
  }
): Promise<{ deck_id: number; message: string }> {
  return fetchApiPublic(`/upload/${encodeURIComponent(token)}/feedback`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function submitDecklistWithUploadLink(
  token: string,
  body: {
    mainboard: { qty: number; card: string }[]
    sideboard?: { qty: number; card: string }[]
    commanders?: string[]
  }
): Promise<{ deck_id: number; message: string }> {
  return fetchApiPublic(`/upload/${encodeURIComponent(token)}/decklist`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function submitDeckWithUploadLink(
  token: string,
  body: {
    player: string
    name: string
    rank?: string
    mainboard: { qty: number; card: string }[]
    sideboard: { qty: number; card: string }[]
    commanders?: string[]
  }
): Promise<{ deck_id: number; message: string }> {
  return fetchApiPublic(`/upload/${encodeURIComponent(token)}`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function updateDeck(
  deckId: number,
  body: {
    name?: string
    player?: string
    rank?: string
    archetype?: string
    event_id?: number | string
    commanders?: string[]
    mainboard?: { qty: number; card: string }[]
    sideboard?: { qty: number; card: string }[]
  }
): Promise<{ deck_id: number; message: string }> {
  return fetchApi(`/decks/${deckId}`, { method: 'PUT', body: JSON.stringify(body) })
}

export async function getDeckMatchups(deckId: number): Promise<{
  matchups: Array<{
    id: number
    deck_id: number
    opponent_player: string
    opponent_deck_id: number | null
    opponent_archetype: string | null
    result: string
    result_note: string
    round: number | null
  }>
  opponent_reported_matchups?: Array<{ opponent_player: string; result: string; intentional_draw?: boolean }>
}> {
  return fetchApi(`/decks/${deckId}/matchups`)
}

export async function updateDeckMatchups(
  deckId: number,
  body: { matchups: Array<{ opponent_player: string; result: string }> }
): Promise<{ deck_id: number; message: string }> {
  return fetchApi(`/decks/${deckId}/matchups`, { method: 'PUT', body: JSON.stringify(body) })
}

export async function deleteDeck(deckId: number): Promise<{ deck_id: number; message: string }> {
  return fetchApi(`/decks/${deckId}`, { method: 'DELETE' })
}

export async function importDeckFromMoxfield(url: string): Promise<{
  commanders: string[]
  mainboard: { qty: number; card: string }[]
  sideboard: { qty: number; card: string }[]
  name?: string | null
  format?: string | null
}> {
  return fetchApi('/decks/import-moxfield', { method: 'POST', body: JSON.stringify({ url }) })
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
  eventId?: number | string | null,
  eventIds?: string | null,
  top8Only?: boolean,
  includeTop8Breakdown?: boolean
): Promise<MetagameReport> {
  const params = new URLSearchParams()
  params.set('placement_weighted', String(placementWeighted))
  params.set('ignore_lands', String(ignoreLands))
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  if (eventIds) params.set('event_ids', eventIds)
  else if (eventId != null) params.set('event_id', String(eventId))
  if (top8Only) params.set('top8_only', 'true')
  if (includeTop8Breakdown) params.set('include_top8_breakdown', 'true')
  return fetchApi(`/metagame?${params.toString()}`)
}

export async function getArchetypeDetail(
  archetypeName: string,
  params?: {
    dateFrom?: string | null
    dateTo?: string | null
    eventIds?: string | null
    ignoreLands?: boolean
  }
): Promise<ArchetypeDetail> {
  const search = new URLSearchParams()
  if (params?.dateFrom) search.set('date_from', params.dateFrom)
  if (params?.dateTo) search.set('date_to', params.dateTo)
  if (params?.eventIds) search.set('event_ids', params.eventIds)
  if (params?.ignoreLands !== undefined) search.set('ignore_lands', String(params.ignoreLands))
  const q = search.toString()
  return fetchApi(`/archetypes/${encodeURIComponent(archetypeName)}${q ? `?${q}` : ''}`)
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
  /** True when DB has an email stored for this player (admin only). */
  has_email?: boolean
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

export async function getIgnoreLandsCards(): Promise<{ cards: string[] }> {
  return fetchApi('/settings/ignore-lands-cards')
}

export async function putIgnoreLandsCards(cards: string[]): Promise<{ cards: string[] }> {
  return fetchApi('/settings/ignore-lands-cards', {
    method: 'PUT',
    body: JSON.stringify({ cards }),
  })
}

export async function getRankWeights(): Promise<{ weights: Record<string, number> }> {
  return fetchApi('/settings/rank-weights')
}

export async function putRankWeights(weights: Record<string, number>): Promise<{ weights: Record<string, number> }> {
  return fetchApi('/settings/rank-weights', {
    method: 'PUT',
    body: JSON.stringify({ weights }),
  })
}

export async function clearScryfallCache(): Promise<{ message: string }> {
  return fetchApi('/settings/clear-cache', { method: 'POST' })
}

export async function clearDecks(): Promise<{ message: string }> {
  return fetchApi('/settings/clear-decks', { method: 'POST' })
}

export type UploadLinkRow = {
  token: string
  event_id: string
  deck_id: number | null
  created_at: string | null
  used_at: string | null
  expires_at: string | null
  label: string | null
}

export async function getUploadLinks(): Promise<{ links: UploadLinkRow[] }> {
  return fetchApi('/settings/upload-links')
}

export async function clearUploadLinks(usedOnly: boolean): Promise<{ deleted: number; message: string }> {
  const params = usedOnly ? '?used_only=true' : ''
  return fetchApi(`/settings/upload-links${params}`, { method: 'DELETE' })
}

export async function getSimilarPlayers(name: string, limit = 10): Promise<{ similar: string[] }> {
  return fetchApi(`/players/similar?name=${encodeURIComponent(name)}&limit=${limit}`)
}

export async function loadDecks(file: File): Promise<{ loaded: number; message: string }> {
  const form = new FormData()
  form.append('file', file)
  return fetchWithAuth('/load', { method: 'POST', body: form }, 'json') as Promise<{
    loaded: number
    message: string
  }>
}

export async function exportDecks(): Promise<Blob> {
  return fetchWithAuth('/export', {}, 'blob') as Promise<Blob>
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

export async function stopScrape(): Promise<{ message: string }> {
  return fetchApi('/scrape/stop', { method: 'POST' })
}
