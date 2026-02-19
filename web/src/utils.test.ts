import { describe, it, expect } from 'vitest'
import { dateMinusDays, pluralizeType } from './utils'

describe('dateMinusDays', () => {
  it('subtracts days correctly', () => {
    expect(dateMinusDays('15/02/26', 14)).toBe('01/02/26')
    expect(dateMinusDays('15/02/26', 30)).toBe('16/01/26')
  })

  it('handles month boundary', () => {
    expect(dateMinusDays('01/02/25', 1)).toBe('31/01/25')
  })
})

describe('pluralizeType', () => {
  it('pluralizes common types with s', () => {
    expect(pluralizeType('Creature')).toBe('Creatures')
    expect(pluralizeType('Instant')).toBe('Instants')
  })

  it('uses PLURAL_MAP for irregular forms', () => {
    expect(pluralizeType('Sorcery')).toBe('Sorceries')
    expect(pluralizeType('Other')).toBe('Other')
  })
})
