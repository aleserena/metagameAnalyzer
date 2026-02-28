export interface DeckCard {
  qty: number
  card: string
}

export interface Deck {
  deck_id: number
  event_id: number | string  // scraped: numeric string "80454"; manual: "m1", "m2"
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
  /** Commander-based color identity (WUBRG), when available. */
  color_identity?: string[]
  duplicate_info?: DeckDuplicateInfo
  /** True if this player has an email stored (admin event view only). */
  has_email?: boolean
}

export interface MetagameSummary {
  total_decks: number
  unique_players: number
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
  /** Commander-based color identity (WUBRG), when available. */
  colors?: string[]
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

export interface ColorDeckCount {
  name: string
  count: number
}

export interface ColorDistribution {
  color: string
  count: number
  pct: number
  /** Top commanders/decks in this color (for tooltip). */
  top_decks?: ColorDeckCount[]
}

export interface ColorCountDistribution {
  label: string
  count: number
  pct: number
  /** Top commanders/decks in this color-count bucket (for tooltip). */
  top_decks?: ColorDeckCount[]
}

export interface MetagameReport {
  summary: MetagameSummary
  commander_distribution: CommanderDistribution[]
  archetype_distribution: ArchetypeDistribution[]
  color_distribution: ColorDistribution[]
  /** Metagame share by number of colors (Monocolor, 2-color, etc.). */
  color_count_distribution?: ColorCountDistribution[]
  top_cards_main: TopCard[]
  /** Top players by wins (same filter as metagame). */
  top_players?: PlayerStats[]
  card_synergy?: CardSynergy[]
  placement_weighted: boolean
  ignore_lands: boolean
  /** When requested with include_top8_breakdown. */
  summary_top8?: MetagameSummary
  archetype_distribution_top8?: ArchetypeDistribution[]
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
  event_id: number | string  // scraped: "80454"; manual: "m1", "m2"
  event_name: string
  store?: string
  location?: string
  date: string
  format_id: string
  player_count?: number  // number of players in the event
  /** 'mtgtop8' | 'manual' — used for merge rules (cannot merge two mtgtop8) */
  origin?: 'mtgtop8' | 'manual'
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
  mana_curve_permanent?: Record<string, number>
  mana_curve_non_permanent?: Record<string, number>
  color_distribution: Record<string, number>
  lands_distribution: { lands: number; nonlands: number }
  type_distribution: Record<string, number>
}

export interface ArchetypeDetail {
  archetype: string
  deck_count: number
  deck_count_top8?: number
  average_analysis: ArchetypeAverageAnalysis
  top_cards_main: TopCard[]
}
