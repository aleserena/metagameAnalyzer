import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { dateMinusDays, dateSortKey, dateInRange, firstDayOfYear, getErrorMessage, pluralizeType, reportError } from './utils'

describe('getErrorMessage', () => {
  const genericMessage = 'There was an issue with the application, please refresh the page'

  it('returns generic message for empty or generic phrases', () => {
    expect(getErrorMessage(new Error(''))).toBe(genericMessage)
    expect(getErrorMessage(new Error('internal server error'))).toBe(genericMessage)
    expect(getErrorMessage(new Error('Internal Server Error'))).toBe(genericMessage)
    expect(getErrorMessage(new Error('failed to fetch'))).toBe(genericMessage)
    expect(getErrorMessage(new Error('not found'))).toBe(genericMessage)
    expect(getErrorMessage(new Error('  '))).toBe(genericMessage)
  })

  it('returns original message for specific errors', () => {
    expect(getErrorMessage(new Error('Player not found'))).toBe('Player not found')
    expect(getErrorMessage(new Error('Invalid JSON: Expecting value'))).toBe('Invalid JSON: Expecting value')
    expect(getErrorMessage(new Error('Deck not found'))).toBe('Deck not found')
  })

  it('handles non-Error values', () => {
    expect(getErrorMessage('something went wrong')).toBe('something went wrong')
    expect(getErrorMessage(null)).toBe(genericMessage)
    expect(getErrorMessage(undefined)).toBe(genericMessage)
  })
})

describe('reportError', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('logs the error and returns user-facing message', () => {
    const err = new Error('internal server error')
    const msg = reportError(err)
    expect(console.error).toHaveBeenCalledWith('[App error]', err)
    expect(msg).toBe('There was an issue with the application, please refresh the page')
  })

  it('returns specific message for non-generic errors', () => {
    const err = new Error('Player not found')
    const msg = reportError(err)
    expect(console.error).toHaveBeenCalledWith('[App error]', err)
    expect(msg).toBe('Player not found')
  })
})

describe('dateSortKey', () => {
  it('returns YYMMDD for DD/MM/YY', () => {
    expect(dateSortKey('15/02/26')).toBe('260215')
    expect(dateSortKey('01/12/25')).toBe('251201')
  })
})

describe('dateInRange', () => {
  it('returns true when no from/to', () => {
    expect(dateInRange('15/02/26', null, null)).toBe(true)
  })

  it('returns true when date is within range', () => {
    expect(dateInRange('15/02/26', '01/02/26', '28/02/26')).toBe(true)
    expect(dateInRange('01/02/26', '01/02/26', '28/02/26')).toBe(true)
    expect(dateInRange('28/02/26', '01/02/26', '28/02/26')).toBe(true)
  })

  it('returns false when date is outside range', () => {
    expect(dateInRange('31/01/26', '01/02/26', '28/02/26')).toBe(false)
    expect(dateInRange('01/03/26', '01/02/26', '28/02/26')).toBe(false)
  })
})

describe('dateMinusDays', () => {
  it('subtracts days correctly', () => {
    expect(dateMinusDays('15/02/26', 14)).toBe('01/02/26')
    expect(dateMinusDays('15/02/26', 30)).toBe('16/01/26')
  })

  it('handles month boundary', () => {
    expect(dateMinusDays('01/02/25', 1)).toBe('31/01/25')
  })
})

describe('firstDayOfYear', () => {
  it('returns 01/01/YY for given date', () => {
    expect(firstDayOfYear('15/06/26')).toBe('01/01/26')
    expect(firstDayOfYear('01/12/25')).toBe('01/01/25')
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
