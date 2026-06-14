import { describe, expect, it } from 'vitest'
import { cmcBucket, colorCategory, getCardTypes } from './topCards'

describe('getCardTypes', () => {
  it('returns ["Other"] for undefined or empty type_line', () => {
    expect(getCardTypes(undefined)).toEqual(['Other'])
    expect(getCardTypes('')).toEqual(['Other'])
  })

  it('extracts a single type', () => {
    expect(getCardTypes('Creature — Elf Druid')).toEqual(['Creature'])
  })

  it('extracts multiple types in TYPE_ORDER, not source order', () => {
    // "Enchantment Land" -> Land comes before Enchantment? No: TYPE_ORDER is
    // [Land, Creature, Instant, Sorcery, Enchantment, ...], so Land precedes Enchantment.
    expect(getCardTypes('Enchantment Land — Saga')).toEqual(['Land', 'Enchantment'])
  })

  it('is case-insensitive', () => {
    expect(getCardTypes('artifact creature — golem')).toEqual(['Creature', 'Artifact'])
  })

  it('falls back to ["Other"] for unrecognized type lines', () => {
    expect(getCardTypes('Conspiracy')).toEqual(['Other'])
  })
})

describe('colorCategory', () => {
  it('treats no colors as Colorless', () => {
    expect(colorCategory(undefined)).toBe('Colorless')
    expect(colorCategory([])).toBe('Colorless')
  })

  it('returns the single color', () => {
    expect(colorCategory(['U'])).toBe('U')
  })

  it('returns Multicolor for 2+ colors', () => {
    expect(colorCategory(['U', 'R'])).toBe('Multicolor')
    expect(colorCategory(['W', 'U', 'B', 'R', 'G'])).toBe('Multicolor')
  })
})

describe('cmcBucket', () => {
  it('buckets non-numbers and negatives to 0', () => {
    expect(cmcBucket(undefined)).toBe(0)
    expect(cmcBucket(-3)).toBe(0)
  })

  it('passes through 0–4 unchanged', () => {
    expect(cmcBucket(0)).toBe(0)
    expect(cmcBucket(4)).toBe(4)
  })

  it('caps everything 5 and above at 5 (the "5+" bucket)', () => {
    expect(cmcBucket(5)).toBe(5)
    expect(cmcBucket(9)).toBe(5)
  })
})
