import { describe, it, expect } from 'vitest'
import {
  isSectionHeader,
  stripSetAndFoiling,
  parseMoxfieldDeckList,
  formatMoxfieldDeckList,
} from './deckListParser'

describe('isSectionHeader', () => {
  it('recognizes Commander without colon', () => {
    expect(isSectionHeader('Commander')).toBe('commander')
    expect(isSectionHeader('commander')).toBe('commander')
    expect(isSectionHeader('EDH')).toBe('commander')
  })

  it('recognizes Commander with colon', () => {
    expect(isSectionHeader('Commander:')).toBe('commander')
    expect(isSectionHeader('commander:')).toBe('commander')
    expect(isSectionHeader('EDH:')).toBe('commander')
  })

  it('recognizes Mainboard with and without colon', () => {
    expect(isSectionHeader('Mainboard')).toBe('main')
    expect(isSectionHeader('Mainboard:')).toBe('main')
    expect(isSectionHeader('Main deck')).toBe('main')
    expect(isSectionHeader('Main deck:')).toBe('main')
    expect(isSectionHeader('Deck')).toBe('main')
  })

  it('recognizes Sideboard with and without colon', () => {
    expect(isSectionHeader('Sideboard')).toBe('side')
    expect(isSectionHeader('Sideboard:')).toBe('side')
    expect(isSectionHeader('SB')).toBe('side')
    expect(isSectionHeader('SB:')).toBe('side')
  })

  it('returns null for card lines', () => {
    expect(isSectionHeader('1 Lightning Bolt')).toBe(null)
    expect(isSectionHeader('Sol Ring')).toBe(null)
    expect(isSectionHeader('Commander 1')).toBe(null)
  })
})

describe('stripSetAndFoiling', () => {
  it('strips (SET) and (SET) number from end', () => {
    expect(stripSetAndFoiling('Ashling, the Limitless (ECC) 1')).toBe('Ashling, the Limitless')
    expect(stripSetAndFoiling('Sol Ring (C21)')).toBe('Sol Ring')
    expect(stripSetAndFoiling('Lightning Bolt (2ED) 100')).toBe('Lightning Bolt')
  })

  it('strips foiling markers *F* *C* from end', () => {
    expect(stripSetAndFoiling('Ashling, the Limitless *F*')).toBe('Ashling, the Limitless')
    expect(stripSetAndFoiling('Sol Ring *F* *C*')).toBe('Sol Ring')
  })

  it('strips (SET) number and foiling together', () => {
    expect(stripSetAndFoiling('Ashling, the Limitless (ECC) 1 *F*')).toBe(
      'Ashling, the Limitless'
    )
  })

  it('leaves card name unchanged when no set/foiling', () => {
    expect(stripSetAndFoiling('Lightning Bolt')).toBe('Lightning Bolt')
    expect(stripSetAndFoiling('Sol Ring')).toBe('Sol Ring')
  })
})

describe('parseMoxfieldDeckList', () => {
  it('parses Commander / Mainboard / Sideboard sections', () => {
    const text = `Commander
1 Atraxa

Mainboard
1 Sol Ring
2 Lightning Bolt

Sideboard
2 Negate`
    const out = parseMoxfieldDeckList(text)
    expect(out.commanders).toEqual([{ qty: 1, card: 'Atraxa' }])
    expect(out.mainboard).toEqual([
      { qty: 1, card: 'Sol Ring' },
      { qty: 2, card: 'Lightning Bolt' },
    ])
    expect(out.sideboard).toEqual([{ qty: 2, card: 'Negate' }])
  })

  it('accepts section headers with colon', () => {
    const text = `Commander:
1 Atraxa

Mainboard:
1 Sol Ring

Sideboard:
1 Negate`
    const out = parseMoxfieldDeckList(text)
    expect(out.commanders).toEqual([{ qty: 1, card: 'Atraxa' }])
    expect(out.mainboard).toEqual([{ qty: 1, card: 'Sol Ring' }])
    expect(out.sideboard).toEqual([{ qty: 1, card: 'Negate' }])
  })

  it('strips (SET) number and *F* from card lines', () => {
    const text = `Mainboard
1 Ashling, the Limitless (ECC) 1 *F*
2 Sol Ring (C21) *F*`
    const out = parseMoxfieldDeckList(text)
    expect(out.mainboard).toEqual([
      { qty: 1, card: 'Ashling, the Limitless' },
      { qty: 2, card: 'Sol Ring' },
    ])
  })

  it('treats missing quantity as 1', () => {
    const text = `Mainboard
Sol Ring
2 Lightning Bolt`
    const out = parseMoxfieldDeckList(text)
    expect(out.mainboard).toEqual([
      { qty: 1, card: 'Sol Ring' },
      { qty: 2, card: 'Lightning Bolt' },
    ])
  })

  it('defaults to mainboard when no section header', () => {
    const text = `1 Sol Ring
Lightning Bolt`
    const out = parseMoxfieldDeckList(text)
    expect(out.commanders).toEqual([])
    expect(out.mainboard).toEqual([
      { qty: 1, card: 'Sol Ring' },
      { qty: 1, card: 'Lightning Bolt' },
    ])
    expect(out.sideboard).toEqual([])
  })
})

describe('formatMoxfieldDeckList', () => {
  it('formats commanders, mainboard, sideboard', () => {
    const text = formatMoxfieldDeckList(
      ['Atraxa'],
      [
        { qty: 1, card: 'Sol Ring' },
        { qty: 2, card: 'Lightning Bolt' },
      ],
      [{ qty: 2, card: 'Negate' }]
    )
    expect(text).toContain('Commander')
    expect(text).toContain('1 Atraxa')
    expect(text).toContain('Mainboard')
    expect(text).toContain('1 Sol Ring')
    expect(text).toContain('2 Lightning Bolt')
    expect(text).toContain('Sideboard')
    expect(text).toContain('2 Negate')
  })
})
