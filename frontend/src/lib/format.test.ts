import { describe, expect, it } from 'vitest'

import { day, initials, listing, numberWord, parseDate, period, plural, safeUrl, slugOf, someOf, trim } from './format'

describe('wording, as the static site words it', () => {
  it('counts with the right noun', () => {
    expect(plural(1, 'story', 'stories')).toBe('1 story')
    expect(plural(3, 'story', 'stories')).toBe('3 stories')
    expect(plural(1751, 'article')).toBe('1,751 articles')
  })

  it('lists names in plain English', () => {
    expect(listing(['KBC'])).toBe('KBC')
    expect(listing(['KBC', 'Capital FM'])).toBe('KBC and Capital FM')
    expect(listing(['KBC', 'Capital FM', 'Nation Africa'])).toBe('KBC, Capital FM and Nation Africa')
  })

  it('says how many of the facts', () => {
    expect(someOf(1, 1)).toBe('The one fact found was')
    expect(someOf(1, 5)).toBe('1 of the 5 facts was')
    expect(someOf(4, 5)).toBe('4 of the 5 facts were')
  })

  it('cuts text at a sentence end or a word, never mid-word', () => {
    const text = 'The death toll rose to 47 on Tuesday. Rescue teams are still searching the area for survivors today'
    expect(trim(text, 55)).toBe('The death toll rose to 47 on Tuesday.')
    expect(trim('from 2015 to 2026 the levy rose sharply', 12)).toBe('from 2015…')
    expect(trim('  short   text ', 50)).toBe('short text')
  })

  it('reads stored dates with a space and API dates with a T, in Kenyan time', () => {
    expect(parseDate('2026-10-22 18:05:23+03:00')?.toISOString()).toBe('2026-10-22T15:05:23.000Z')
    expect(day('2026-10-27T23:30:00+03:00')).toBe('27 Oct')
    expect(day('2026-10-27T22:30:00Z')).toBe('28 Oct')
    expect(period('2026-08-21T09:00:00+03:00', '2026-10-27T16:30:00+03:00')).toBe('21 Aug to 27 Oct 2026')
    expect(parseDate('not a date')).toBeNull()
  })

  it('gives an outlet its initials and its link name', () => {
    expect(initials('Nation Africa')).toBe('NA')
    expect(initials('The Kenya Times')).toBe('KT')
    expect(initials('KBC')).toBe('KB')
    expect(slugOf('The Kenya Times')).toBe('the-kenya-times')
    expect(slugOf('Business Daily Africa')).toBe('business-daily-africa')
  })

  it('lets only web links through (DEF-27)', () => {
    expect(safeUrl('https://www.kbc.co.ke/a')).toBe('https://www.kbc.co.ke/a')
    expect(safeUrl(' http://nation.africa/b ')).toBe('http://nation.africa/b')
    expect(safeUrl('javascript:alert(1)')).toBeNull()
    expect(safeUrl('JavaScript:alert(1)')).toBeNull()
    expect(safeUrl('data:text/html,hi')).toBeNull()
    expect(safeUrl('//evil.example')).toBeNull()
    expect(safeUrl(null)).toBeNull()
  })

  it('spells small numbers for the headline', () => {
    expect(numberWord(12)).toBe('twelve')
    expect(numberWord(25)).toBe('25')
  })
})
