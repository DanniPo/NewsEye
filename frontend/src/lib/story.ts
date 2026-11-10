// What a story page shows, computed from the API's story. Ported from
// backend/scripts/build_site.py: same rules, same words.

import type {
  Article,
  FactGroup,
  Figure,
  FramingRecord,
  QuoteRelation,
  Remark,
  Story,
  StorySummary,
} from '../api/types'
import { capitalise, day, listing, plural, someOf, trim } from './format'

export type TabId = 'overview' | 'facts' | 'quotes' | 'tone' | 'numbers'

export interface Outlets {
  /** outlets whose article could be opened */
  read: string[]
  /** outlets none of whose articles could be opened (paywall or blocked) */
  unread: string[]
  /** false for an analysis stored before the flags were recorded */
  recorded: boolean
}

/**
 * Which outlets could be read. An outlet with one readable article and one
 * blocked one was read, and is not also listed as unread. Without the flags the
 * story's outlets are all listed as read, and the page says it cannot tell.
 */
export function readOutlets(story: Story): Outlets {
  const { recorded, readable_outlets, unread_outlets } = story.readability
  if (recorded) {
    return { read: [...(readable_outlets ?? [])], unread: [...(unread_outlets ?? [])], recorded }
  }
  return { read: [...story.outlets].sort(), unread: [], recorded: false }
}

/** Facts that not every readable outlet reported word for word. */
export function gapsIn(coverage: readonly FactGroup[]): number {
  return coverage.filter((g) => (g.omitted_by?.length ?? 0) > 0 || (g.related?.length ?? 0) > 0)
    .length
}

export type Cell = 'reported' | 'similar' | 'not reported'

export interface FactRow {
  text: string
  status: string
  cells: Record<string, Cell>
  related: { source: string; text: string }[]
}

/** Facts down the side, the outlets that could be read across the top. */
export function coverageRows(coverage: readonly FactGroup[], read: readonly string[]) {
  const carried: Record<string, number> = Object.fromEntries(read.map((o) => [o, 0]))
  const rows: FactRow[] = coverage.map((group) => {
    const reported = new Set(group.reported_by ?? [])
    // analyses saved before the inference check have no "related"
    const related = new Map((group.related ?? []).map((r) => [r.source, r.text]))
    const cells: Record<string, Cell> = {}
    for (const outlet of read) {
      if (reported.has(outlet)) {
        cells[outlet] = 'reported'
        carried[outlet] += 1
      } else if (related.has(outlet)) {
        cells[outlet] = 'similar'
      } else {
        cells[outlet] = 'not reported'
      }
    }
    const by = read.filter((o) => reported.has(o)).length
    const similar = read.filter((o) => related.has(o) && !reported.has(o)).length
    return {
      text: trim(group.anchor.text, 170),
      status: `Reported by ${by} of ${read.length}${similar ? ` · similar in ${similar}` : ''}`,
      cells,
      related: [...related].map(([source, text]) => ({ source, text: trim(text, 220) })),
    }
  })
  return { rows, carried, total: coverage.length }
}

export interface GlancePoint {
  text: string
  link?: { tab: TabId; label: string }
}

/** "Counter.most_common": by count, then first seen. */
function mostCommon(values: readonly string[]): [string, number][] {
  const counts = new Map<string, number>()
  for (const value of values) counts.set(value, (counts.get(value) ?? 0) + 1)
  return [...counts].sort((a, b) => b[1] - a[1])
}

/** The comparison in three or four sentences, each counting something a tab shows. */
export function glancePoints(story: Story): GlancePoint[] {
  const { read, unread } = readOutlets(story)
  const total = read.length + unread.length
  const points: GlancePoint[] = [
    unread.length
      ? {
          text: `We could open ${read.length} of the ${total} outlets' articles. ${listing(unread)} could not be opened (paywall or blocked).`,
        }
      : { text: `We could open all ${total} outlets' articles.` },
  ]
  const analysis = story.analysis
  if (!analysis) return points

  const groups = analysis.coverage
  if (groups.length) {
    const alone = mostCommon(
      groups.filter((g) => (g.reported_by ?? []).length === 1).map((g) => g.reported_by![0]),
    )
    const gaps = gapsIn(groups)
    if (!gaps) {
      points.push({ text: `Every outlet we could open reported the same ${plural(groups.length, 'fact')}.` })
    } else if (alone.length) {
      const only = alone.reduce((sum, [, n]) => sum + n, 0)
      const who = alone.length === 1
        ? `only by ${alone[0][0]}`
        : `by only one outlet: ${alone.map(([o, n]) => `${o} ${n}`).join(', ')}`
      const rest = gaps - only
      const more = rest > 0
        ? ` ${plural(rest, 'other fact')} ${rest === 1 ? 'was' : 'were'} left out by at least one outlet.`
        : ''
      points.push({
        text: `${someOf(only, groups.length)} reported ${who}.${more}`,
        link: { tab: 'facts', label: 'See which' },
      })
    } else {
      points.push({
        text: `${someOf(gaps, groups.length)} left out by at least one outlet.`,
        link: { tab: 'facts', label: 'See which' },
      })
    }
  }

  const shared = analysis.quotes.filter((r) => r.outlets > 1)
  if (shared.length) {
    const same = shared.filter((r) => r.versions.every((v) => v.relation === 'first' || v.relation === 'same')).length
    const changed = shared.filter((r) => r.versions.some((v) => CHANGED.has(v.relation))).length
    const how = [same ? `${same} word for word` : '', changed ? `${changed} in different words` : ''].filter(Boolean)
    points.push({
      text: `${plural(shared.length, 'remark')} ${shared.length === 1 ? 'was' : 'were'} quoted by more than one outlet${how.length ? `: ${how.join(' and ')}` : ''}.`,
      link: { tab: 'quotes', label: 'Compare them' },
    })
  }

  const numbers = analysis.numbers.groups.length
  if (numbers) {
    points.push({
      text: `${plural(numbers, 'number')} ${numbers === 1 ? 'was' : 'were'} given by more than one outlet.`,
      link: { tab: 'numbers', label: 'See them side by side' },
    })
  }
  return points
}

const CHANGED = new Set<QuoteRelation>(['says more', 'says less', 'worded differently'])

export const QUOTE_RELATION: Record<QuoteRelation, { label: string; tone: string }> = {
  first: { label: 'First version', tone: 'q-none' },
  same: { label: 'Same words', tone: 'q-same' },
  'says more': { label: 'Adds to it', tone: 'q-more' },
  'says less': { label: 'Shorter version', tone: 'q-less' },
  'worded differently': { label: 'Worded differently', tone: 'q-diff' },
  'not compared': { label: 'Not compared', tone: 'q-none' },
}

/** remarks shown open; the rest are one click away */
export const SHOWN_REMARKS = 2

export function splitRemarks(remarks: readonly Remark[]) {
  return {
    shared: remarks.filter((r) => r.outlets > 1),
    single: remarks.filter((r) => r.outlets === 1),
  }
}

const STRIP = /^[.,;:!?“”"']+|[.,;:!?“”"']+$/g

/**
 * The words of `text`, each marked if `other` does not have it: what a longer
 * version of a quote adds. Longest common subsequence over the words, ignoring
 * case and surrounding punctuation.
 */
export function markAdded(text: string, other: string): { word: string; added: boolean }[] {
  const words = text.split(/\s+/).filter(Boolean)
  const mine = words.map((w) => w.toLowerCase().replace(STRIP, ''))
  const theirs = other.split(/\s+/).filter(Boolean).map((w) => w.toLowerCase().replace(STRIP, ''))
  const n = mine.length
  const m = theirs.length
  const table = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      table[i][j] = mine[i] === theirs[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1])
    }
  }
  const keep = new Set<number>()
  for (let i = 0, j = 0; i < n && j < m;) {
    if (mine[i] === theirs[j]) {
      keep.add(i)
      i++
      j++
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      i++
    } else {
      j++
    }
  }
  return words.map((word, i) => ({ word, added: !keep.has(i) }))
}

/** Up to three people, each outlet's reading of them, strongest first. */
export function framingRows(framing: readonly FramingRecord[]) {
  const records = framing.filter((f) => f.sources?.length).slice(0, 3)
  const rows = records.map((record) => {
    const entries = [...record.sources].sort((a, b) => b.score - a.score)
    // NewsMTSC scores people only; a place or body was read from its sentences' tone
    const sentenceOnly = entries.every((s) => (s.scored_by ?? 'sentence') === 'sentence')
    return { entity: record.entity, entries, sentenceOnly }
  })
  const targeted = rows.some((r) => r.entries.some((s) => s.scored_by === 'targeted' || s.scored_by === 'mixed'))
  return { rows, targeted }
}

/** The tags beside a figure: who it is credited to, running total, currency, parts. */
export function figureTags(row: Figure): string[] {
  const tags: string[] = []
  if (row.credited_to) tags.push(`according to ${row.credited_to}`)
  if (row.cumulative) tags.push('running total')
  if (row.currency && row.currency !== 'unspecified') tags.push(row.currency.toUpperCase())
  if (row.breakdown.length) tags.push(`of which ${row.breakdown.slice(0, 3).join(', ')}`)
  return tags
}

/**
 * The figure's passage, cut around the figure, so a figure late in a long passage
 * is not cut off. The figure's own sentence is searched first, so a number that
 * also appears in the sentence before is not the one marked.
 */
export function figureInContext(row: Figure, limit = 280) {
  const squash = (s: string | null | undefined) => (s ?? '').split(/\s+/).filter(Boolean).join(' ')
  const text = squash(row.context || row.sentence)
  const figure = squash(row.figure)
  const sentence = squash(row.sentence)
  const base = sentence ? text.indexOf(sentence) : -1
  let at = figure ? text.indexOf(figure, Math.max(base, 0)) : -1
  if (at < 0 && figure) at = text.indexOf(figure)
  if (at < 0) return { before: trim(text, limit), figure: '', after: '', cutStart: false, cutEnd: false }
  let start = Math.max(0, at - Math.floor(limit / 2))
  let end = Math.min(text.length, Math.max(start + limit, at + figure.length))
  if (start > 0) {
    const space = text.indexOf(' ', start)
    start = space >= 0 && space < at ? space + 1 : start
  }
  if (end < text.length) {
    // the last space before the cut, if it falls after the figure
    const cut = text.lastIndexOf(' ', end - 1)
    end = cut >= at + figure.length ? cut : end
  }
  return {
    before: text.slice(start, at),
    figure,
    after: text.slice(at + figure.length, end),
    cutStart: start > 0,
    cutEnd: end < text.length,
  }
}

/** The readable article for each outlet, where it has one; used for "Read" links. */
export function firstArticles(articles: readonly Article[]): Map<string, Article> {
  const first = new Map<string, Article>()
  for (const article of articles) {
    const have = first.get(article.outlet)
    if (!have || (article.readable && !have.readable)) first.set(article.outlet, article)
  }
  return first
}

/**
 * What a story card says under its headline, and its badges. A story with fewer
 * than two readable outlets, or no fact found in two, has nothing to compare: the
 * static site gave it no page, and here its card says why rather than counting
 * "facts not in every outlet", which would present an unread outlet as one that
 * left facts out (NFR-04).
 */
export function cardSummary(story: StorySummary) {
  const analysed = story.status === 'analysed'
  const gaps = story.facts_not_in_every_outlet ?? 0
  const reasons = story.differences?.reasons ?? []
  const readable = story.outlets.length - (story.unread_outlets?.length ?? 0)
  const nothingToCompare = analysed && story.comparable === false
  const badges: { text: string; tone: 'gap' | 'ok' | 'wait' }[] = []
  let line: string
  if (!analysed) {
    badges.push({ text: 'not compared yet', tone: 'wait' })
    line = "Not compared yet: open it to read each outlet's headline."
  } else if (nothingToCompare && readable < 2) {
    badges.push({ text: 'only one outlet could be read', tone: 'wait' })
    line = "Only one outlet's article could be opened, so there is nothing to set beside it yet."
  } else if (nothingToCompare) {
    badges.push({ text: 'no shared facts found', tone: 'wait' })
    line = 'No fact was found in two outlets, so there is nothing to set side by side.'
  } else {
    badges.push(gaps
      ? { text: `${plural(gaps, 'fact')} not in every outlet`, tone: 'gap' }
      : { text: 'same facts in every outlet we read', tone: 'ok' })
    if (reasons.length) line = `${capitalise(reasons.join(' · '))}.`
    else if (gaps) line = 'Some facts appear in only some of the outlets we could read.'
    else line = 'Every outlet we could read reported the same facts.'
  }

  const meta = [plural(story.article_count ?? 0, 'article')]
  if (story.numbers_to_compare) meta.push(`${plural(story.numbers_to_compare, 'number')} to compare`)
  if (story.unread_outlets?.length) meta.push(`${story.unread_outlets.length} could not be read`)
  if (story.latest) meta.push(`latest ${day(story.latest)}`)
  return { badges, line, meta }
}
