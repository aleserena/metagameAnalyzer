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
  /** Stable player identity (API/DB); optional for backward compat. */
  player_id?: number
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
  /** Decks that played this card and made top 8. */
  decks_top8?: number
  /** % of decks that played this card and made top 8 (conversion). */
  conversion_rate_pct?: number
}

export interface HealthReport {
  health_score: number | null
  factors: {
    archetype_diversity: number | null
    top_card_concentration: number | null
    win_rate_parity: number | null
    meta_shift_rate: number | null
    dominant_archetype: number | null
  }
  details: {
    viable_archetype_count: number
    effective_archetype_count: number
    avg_top5_card_inclusion_pct: number
    archetype_win_rate_stddev: number | null
    stability_index: number | null
    top_archetype: string | null
    top_archetype_share_pct: number
  }
}

export interface H2HFormatRecord {
  format_id: string
  wins: number
  losses: number
  draws: number
}

export interface H2HOpponent {
  opponent_player_id: number
  opponent_player: string
  wins: number
  losses: number
  draws: number
  matches: number
  win_pct: number
  formats: H2HFormatRecord[]
}

export interface H2HSummary {
  player_id: number
  opponents: H2HOpponent[]
}

export interface H2HMatch {
  deck_id: number
  event_id: number | string
  event_name: string
  date: string
  format_id: string
  round: number | null
  result: 'win' | 'loss' | 'draw' | 'intentional_draw'
  player_archetype: string | null
  opponent_deck_id: number | null
  opponent_archetype: string | null
}

export interface H2HDetail {
  player_id: number
  opponent_id: number
  opponent_player: string
  wins: number
  losses: number
  draws: number
  matches: H2HMatch[]
}

export interface ChurnWindowSummary {
  deck_count: number
  event_count: number
  date_from: string | null
  date_to: string | null
}

export interface ChurnArchetypeChange {
  archetype: string
  status: 'entered' | 'exited' | 'stable'
  current_rank: number | null
  previous_rank: number | null
  rank_delta: number | null
  current_play_rate_pct: number
  previous_play_rate_pct: number
  play_rate_delta_pct: number
}

export interface ChurnVolatileCard {
  card: string
  current_inclusion_pct: number
  previous_inclusion_pct: number
  delta_pct: number
}

export interface ChurnReport {
  stability_index: number | null
  current_window: ChurnWindowSummary
  previous_window: ChurnWindowSummary
  archetype_changes: ChurnArchetypeChange[]
  most_volatile_cards: ChurnVolatileCard[]
  params: { format: string | null; weeks: number; top_n: number }
  message?: string
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
  player_id?: number
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
  mana_pips_by_color?: Record<string, number>
}

export interface TypicalListEntry {
  card: string
  decks: number
  play_rate_pct: number
  mean_copies: number
  median_copies: number
}

export interface TypicalList {
  core: TypicalListEntry[]
  staple: TypicalListEntry[]
  flex: TypicalListEntry[]
  tech: TypicalListEntry[]
}

export interface ArchetypeDetail {
  archetype: string
  deck_count: number
  deck_count_top8?: number
  average_analysis: ArchetypeAverageAnalysis
  top_cards_main: TopCard[]
  top_players?: PlayerStats[]
  typical_list?: TypicalList
}

export interface CardHeatmapEntry {
  card: string
  category: string
  main_decks: number
  side_decks: number
  main_rate_pct: number
  side_rate_pct: number
  inclusion_rate_pct: number
}

export interface CardHeatmap {
  archetype: string
  deck_count: number
  cards: CardHeatmapEntry[]
}

export interface ArchetypeWeeklyStat {
  week: string
  week_start: string | null
  archetype_decks: number
  archetype_top8: number
  total_decks: number
  share_pct: number
  top8_rate_pct: number
}

export interface ArchetypeWeeklyStats {
  archetype: string
  weeks: ArchetypeWeeklyStat[]
}

export interface CoCommander {
  name: string
  count: number
  pct: number
}

export interface CommanderCardEntry {
  card: string
  inclusion_rate_pct: number
}

export interface CommanderTechCardEntry {
  card: string
  top_rate_pct: number
  overall_rate_pct: number
  delta_pct: number
}

export interface CommanderSynergy {
  commander: string
  deck_count: number
  co_commanders: CoCommander[]
  shell_composition: Record<string, number>
  core_cards: CommanderCardEntry[]
  flex_cards: CommanderCardEntry[]
  tech_cards: CommanderTechCardEntry[]
}
