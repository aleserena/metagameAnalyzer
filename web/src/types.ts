export interface DeckCard {
  qty: number
  card: string
}

export interface Deck {
  deck_id: number
  event_id: number
  format_id: string
  name: string
  player: string
  event_name: string
  date: string
  rank: string
  player_count: number
  mainboard: DeckCard[]
  sideboard: DeckCard[]
  commanders: string[]
  archetype: string | null
  duplicate_info?: DeckDuplicateInfo
}

export interface MetagameSummary {
  total_decks: number
  unique_commanders: number
  unique_archetypes: number
}

export interface CommanderDistribution {
  commander: string
  count: number
  pct: number
}

export interface ArchetypeDistribution {
  archetype: string
  count: number
  pct: number
}

export interface TopCard {
  card: string
  decks: number
  play_rate_pct: number
  total_copies: number
}

export interface CardSynergy {
  card_a: string
  card_b: string
  decks: number
}

export interface MetagameReport {
  summary: MetagameSummary
  commander_distribution: CommanderDistribution[]
  archetype_distribution: ArchetypeDistribution[]
  top_cards_main: TopCard[]
  card_synergy?: CardSynergy[]
  placement_weighted: boolean
  ignore_lands: boolean
}

export interface SimilarDeck {
  deck_id: number
  name: string
  player: string
  event_name: string
  date: string
  rank: string
  similarity: number
}

export interface DeckDuplicateSummary {
  deck_id: number
  name: string
  player: string
  event_name: string
  date: string
  rank?: string
}

export interface DeckDuplicateInfo {
  is_duplicate: boolean
  duplicate_of: number | null
  same_mainboard_ids: number[]
  same_mainboard_decks?: DeckDuplicateSummary[]
  primary_deck?: DeckDuplicateSummary
}

export interface Event {
  event_id: number
  event_name: string
  date: string
  format_id: string
}

export interface PlayerStats {
  player: string
  wins: number
  top2: number
  top4: number
  top8: number
  points: number
  deck_count: number
}

/** Average deck analysis for an archetype (subset of deck analysis fields). */
export interface ArchetypeAverageAnalysis {
  mana_curve: Record<string, number>
  color_distribution: Record<string, number>
  lands_distribution: { lands: number; nonlands: number }
  type_distribution: Record<string, number>
}

export interface ArchetypeDetail {
  archetype: string
  deck_count: number
  average_analysis: ArchetypeAverageAnalysis
  top_cards_main: TopCard[]
}
