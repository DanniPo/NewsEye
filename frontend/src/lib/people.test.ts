import { describe, expect, it } from 'vitest'

import type { MentionRecord } from '../api/types'
import { PERSON } from '../test/fixtures'
import { glanceFacts, overallTitle, personHeadlines, roleSentence, topRole, toneShares, usualTitle } from './people'

const capital = PERSON.outlets['Capital FM']

describe('how an outlet presents a person, in words', () => {
  it("states the outlet's split of roles", () => {
    expect(roleSentence('Ruto', capital)).toBe(
      'Ruto is quoted speaking in 50% of mentions, shown doing something in 30% and named in passing in 20%.')
    expect(topRole(capital)).toBe('speaks')
  })

  it('gives the title most headlines use', () => {
    expect(usualTitle(capital)).toBe('President')
    expect(overallTitle(PERSON)).toBe('President')
  })

  it('picks one headline per role first, then the newest, shown newest first', () => {
    const records: MentionRecord[] = [
      { url: 'a', headline: 'A', date: '2026-10-01 09:00:00+03:00', role: 'acts', field: 'headline' },
      { url: 'b', headline: 'B', date: '2026-10-20 09:00:00+03:00', role: 'speaks', field: 'headline' },
      { url: 'c', headline: 'C', date: '2026-10-21 09:00:00+03:00', role: 'speaks', field: 'headline' },
      { url: 'd', headline: 'D', date: '2026-10-22 09:00:00+03:00', role: 'speaks', field: 'snippet' },
    ]
    expect(personHeadlines(records, 3).map((r) => r.url)).toEqual(['c', 'b', 'a'])
  })

  it('states facts at a glance, not findings', () => {
    const named = Object.entries(PERSON.outlets).sort((a, b) => b[1].articles - a[1].articles)
    const facts = glanceFacts(named, [['The Sharp Daily', 105]])
    const text = facts.map((f) => f.parts.map((p) => p.text).join(''))
    expect(text[0]).toBe('Named most often by Capital FM: 72 of its 609 articles.')
    expect(text[1]).toBe('Never named by The Sharp Daily.')
    expect(text[2]).toBe('Shown speaking most in Capital FM (50% of mentions), least in KBC (10%).')
  })

  it('splits a tone mix so the three shares add up', () => {
    expect(toneShares({ n: 10, negative: 0.2, positive: 0.3 })).toEqual({ negative: 0.2, neutral: 0.5, positive: 0.3 })
  })
})
