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

export interface MetagameReport {
  summary: MetagameSummary
  commander_distribution: CommanderDistribution[]
  archetype_distribution: ArchetypeDistribution[]
  top_cards_main: TopCard[]
  placement_weighted: boolean
  ignore_lands: boolean
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
