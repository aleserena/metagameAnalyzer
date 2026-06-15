import { describe, expect, it } from 'vitest'
import type { CardLookupResult } from '../api'
import {
  canonicalCardNameForCompare,
  defaultDeckEdit,
  getEDHArchetype,
  getPartnerMode,
  normalizeDeckListByLookup,
} from './deckUtils'
import type { ParsedDeckList } from './deckListParser'

describe('canonicalCardNameForCompare', () => {
  it('lowercases for case-insensitive comparison', () => {
    expect(canonicalCardNameForCompare('Sol Ring')).toBe('sol ring')
  })

  it('uses the front face of double-faced cards (split on " // ")', () => {
    expect(canonicalCardNameForCompare('Fable of the Mirror-Breaker // Reflection of Kiki-Jiki')).toBe(
      'fable of the mirror-breaker'
    )
  })

  it('trims whitespace', () => {
    expect(canonicalCardNameForCompare('  Lightning Bolt  ')).toBe('lightning bolt')
  })

  it('returns empty string for non-string / nullish input', () => {
    expect(canonicalCardNameForCompare(null as unknown as string)).toBe('')
    expect(canonicalCardNameForCompare(undefined as unknown as string)).toBe('')
  })
})

describe('getEDHArchetype', () => {
  it('returns undefined with no commanders', () => {
    expect(getEDHArchetype([], null)).toBeUndefined()
  })

  it('returns the single commander name as-is', () => {
    expect(getEDHArchetype(['Krenko, Mob Boss'], null)).toBe('Krenko, Mob Boss')
  })

  it('returns undefined for 2+ commanders without a lookup', () => {
    expect(getEDHArchetype(['A', 'B'], null)).toBeUndefined()
  })

  it('builds "Partner {Colors}" in WUBRG order from color identity', () => {
    const lookup: Record<string, CardLookupResult> = {
      'Tana, the Bloodsower': { color_identity: ['G', 'R'] } as CardLookupResult,
      'Tymna the Weaver': { color_identity: ['W', 'B'] } as CardLookupResult,
    }
    expect(getEDHArchetype(['Tana, the Bloodsower', 'Tymna the Weaver'], lookup)).toBe('Partner WBRG')
  })

  it('skips commanders whose lookup errored and falls back to colors', () => {
    const lookup: Record<string, CardLookupResult> = {
      Good: { colors: ['U'] } as CardLookupResult,
      Bad: { error: 'not found' } as unknown as CardLookupResult,
    }
    expect(getEDHArchetype(['Good', 'Bad'], lookup)).toBe('Partner U')
  })

  it('returns bare "Partner" when no colors resolve', () => {
    const lookup: Record<string, CardLookupResult> = {
      X: { color_identity: [] } as CardLookupResult,
      Y: { color_identity: [] } as CardLookupResult,
    }
    expect(getEDHArchetype(['X', 'Y'], lookup)).toBe('Partner')
  })
})

describe('getPartnerMode', () => {
  const entry = (oracle_text: string, type_line = 'Legendary Creature'): CardLookupResult =>
    ({ oracle_text, type_line }) as CardLookupResult

  it('returns null role for missing or non-partner cards', () => {
    expect(getPartnerMode(undefined).role).toBeNull()
    expect(getPartnerMode(entry('Flying, vigilance')).role).toBeNull()
    expect(getPartnerMode({ error: 'not found' } as unknown as CardLookupResult).role).toBeNull()
  })

  it('detects generic Partner', () => {
    expect(getPartnerMode(entry('Partner (You can have two commanders if both have partner.)')).role).toBe(
      'partner'
    )
  })

  it('detects "Partner with [name]" and extracts the named card', () => {
    const m = getPartnerMode(entry('Partner with Pir, Imaginative Rascal (When this creature enters...)'))
    expect(m.role).toBe('partner_with')
    expect(m.partnerWithName).toBe('Pir, Imaginative Rascal')
  })

  it('detects Choose a Background', () => {
    expect(getPartnerMode(entry('Choose a Background (You can have a Background as a second commander.)')).role).toBe(
      'background'
    )
  })

  it('detects Friends forever', () => {
    expect(getPartnerMode(entry('Friends forever (You can have two commanders if both have friends forever.)')).role).toBe(
      'friends_forever'
    )
  })

  it("maps Doctor's companion to a Time Lord Doctor secondary, and vice versa", () => {
    expect(getPartnerMode(entry("Doctor's companion (You can have two commanders...)")).role).toBe(
      'time_lord_doctor'
    )
    expect(getPartnerMode(entry('Flying', 'Legendary Creature — Time Lord Doctor')).role).toBe(
      'doctors_companion'
    )
  })
})

describe('normalizeDeckListByLookup', () => {
  it('replaces card names with canonical lookup names and reformats text', () => {
    const parsed: ParsedDeckList = {
      commanders: [{ qty: 1, card: 'Krenko' }],
      mainboard: [{ qty: 4, card: 'Bolt' }],
      sideboard: [],
    }
    const lookup: Record<string, CardLookupResult> = {
      Krenko: { name: 'Krenko, Mob Boss' } as CardLookupResult,
      Bolt: { name: 'Lightning Bolt' } as CardLookupResult,
    }
    const { parsed: out, text } = normalizeDeckListByLookup(parsed, lookup)
    expect(out.commanders[0]!.card).toBe('Krenko, Mob Boss')
    expect(out.mainboard[0]!.card).toBe('Lightning Bolt')
    expect(text).toContain('Lightning Bolt')
    expect(text).toContain('Krenko, Mob Boss')
  })

  it('leaves names unchanged when lookup has no better name', () => {
    const parsed: ParsedDeckList = {
      commanders: [],
      mainboard: [{ qty: 1, card: 'Sol Ring' }],
      sideboard: [],
    }
    const { parsed: out } = normalizeDeckListByLookup(parsed, {})
    expect(out.mainboard[0]!.card).toBe('Sol Ring')
  })
})

describe('defaultDeckEdit', () => {
  it('copies name/player/rank/archetype from the deck', () => {
    const d = { name: 'Boros Aggro', player: 'Jeremy', rank: '1', archetype: 'Aggro' } as Parameters<typeof defaultDeckEdit>[0]
    expect(defaultDeckEdit(d)).toEqual({ name: 'Boros Aggro', player: 'Jeremy', rank: '1', archetype: 'Aggro' })
  })

  it('falls back to the first commander when archetype is missing (EDH)', () => {
    const d = { commanders: ['Krenko, Mob Boss'] } as Parameters<typeof defaultDeckEdit>[0]
    expect(defaultDeckEdit(d).archetype).toBe('Krenko, Mob Boss')
  })

  it('uses empty strings for missing fields', () => {
    const d = {} as Parameters<typeof defaultDeckEdit>[0]
    expect(defaultDeckEdit(d)).toEqual({ name: '', player: '', rank: '', archetype: '' })
  })
})
