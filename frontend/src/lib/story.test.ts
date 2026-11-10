import { describe, expect, it } from 'vitest'

import type { Figure } from '../api/types'
import { CARD, CARD_ONE_READABLE, CARD_WAITING, STORY } from '../test/fixtures'
import { cardSummary, coverageRows, figureInContext, figureTags, gapsIn, glancePoints, markAdded, readOutlets } from './story'

describe('a story compared', () => {
  it('names the outlet it could not open, and never as one that left facts out (NFR-04)', () => {
    const outlets = readOutlets(STORY)
    expect(outlets).toEqual({ read: ['Capital FM', 'The Kenya Times'], unread: ['People Daily'], recorded: true })
    const { rows } = coverageRows(STORY.analysis!.coverage, outlets.read)
    for (const row of rows) expect(Object.keys(row.cells)).not.toContain('People Daily')
  })

  it('marks each fact reported, similar or not reported, and counts per outlet', () => {
    const { rows, carried, total } = coverageRows(STORY.analysis!.coverage, ['Capital FM', 'The Kenya Times'])
    expect(rows[0].cells).toEqual({ 'Capital FM': 'reported', 'The Kenya Times': 'similar' })
    expect(rows[1].cells).toEqual({ 'Capital FM': 'reported', 'The Kenya Times': 'not reported' })
    expect(rows[0].status).toBe('Reported by 1 of 2 · similar in 1')
    expect(carried).toEqual({ 'Capital FM': 2, 'The Kenya Times': 0 })
    expect(total).toBe(2)
    expect(gapsIn(STORY.analysis!.coverage)).toBe(2)
  })

  it('without the opened flags, lists every outlet and says it cannot tell', () => {
    const old = { ...STORY, readability: { recorded: false, readable_outlets: null, unread_outlets: null } }
    expect(readOutlets(old)).toEqual({ read: ['Capital FM', 'People Daily', 'The Kenya Times'], unread: [], recorded: false })
  })

  it('sums the story up in sentences that each point to a tab', () => {
    const points = glancePoints(STORY)
    expect(points[0].text).toBe("We could open 2 of the 3 outlets' articles. People Daily could not be opened (paywall or blocked).")
    expect(points[1]).toEqual({ text: '2 of the 2 facts were reported only by Capital FM.', link: { tab: 'facts', label: 'See which' } })
    expect(points[2].text).toBe('1 remark was quoted by more than one outlet: 1 in different words.')
    expect(points[3]).toEqual({ text: '1 number was given by more than one outlet.', link: { tab: 'numbers', label: 'See them side by side' } })
  })

  it('marks the words a longer version of a quote adds', () => {
    const words = markAdded('This treatment of our citizens is unacceptable, and must stop', 'This treatment is unacceptable and must stop')
    expect(words.filter((w) => w.added).map((w) => w.word)).toEqual(['of', 'our', 'citizens'])
  })

  it('tags a figure with its source, total, currency and parts, and cuts around it', () => {
    const row: Figure = {
      figure: '3.468 million', value: 3468000, unit: 'people', source: 'Nairobi Wire', credited_to: 'Treasury',
      cumulative: true, currency: 'kes', breakdown: ['1.778 million'],
      sentence: "Out of Kenya's 3.468 million formal sector workers, about 1.778 million will pay PAYE.",
      context: 'A long opening passage about the tax change that goes on for a while. ' +
        "Out of Kenya's 3.468 million formal sector workers, about 1.778 million will pay PAYE. Cabinet met later.",
      url: 'https://nairobiwire.com/x',
    }
    expect(figureTags(row)).toEqual(['according to Treasury', 'running total', 'KES', 'of which 1.778 million'])
    const cut = figureInContext(row, 60)
    expect(cut.figure).toBe('3.468 million')
    expect(cut.cutStart).toBe(true)
    expect(`${cut.before}${cut.figure}${cut.after}`).toContain('3.468 million formal')
  })
})

describe('a story card', () => {
  it('says what differs, in words a reader can check', () => {
    const card = cardSummary(CARD)
    expect(card.badges).toEqual([{ text: '2 facts not in every outlet', tone: 'gap' }])
    expect(card.line).toBe('Outlets worded 1 fact differently · tone about Nigeria differs between outlets.')
    expect(card.meta).toEqual(['3 articles', '2 numbers to compare', '1 could not be read', 'latest 27 Oct'])
  })

  it('with one readable outlet, says there is nothing to compare rather than counting gaps (NFR-04)', () => {
    const card = cardSummary(CARD_ONE_READABLE)
    expect(card.badges).toEqual([{ text: 'only one outlet could be read', tone: 'wait' }])
    expect(card.line).toMatch(/nothing to set beside it/)
  })

  it('a story not yet compared claims nothing', () => {
    const card = cardSummary(CARD_WAITING)
    expect(card.badges).toEqual([{ text: 'not compared yet', tone: 'wait' }])
  })
})
