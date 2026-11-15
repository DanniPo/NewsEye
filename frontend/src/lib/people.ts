// How each outlet presents a person, in words. Ported from build_site.py's people
// pages, so both sites describe a person the same way.

import type { MentionRecord, OutletPortrayal, Person, Role, Tone } from '../api/types'
import { count, listing, parseDate, percent } from './format'

/** How a headline presents the person, in the same words everywhere on the page. */
export const ROLE_ORDER: { role: Role; words: string; meaning: string }[] = [
  { role: 'speaks', words: 'quoted speaking', meaning: 'the headline reports their words' },
  { role: 'acts', words: 'shown doing something', meaning: 'they are the one acting' },
  { role: 'acted on', words: 'on the receiving end', meaning: 'something is done or said to them' },
  { role: 'spoken about', words: 'talked about by others', meaning: "they appear inside someone else's quoted words" },
  { role: 'described', words: 'described', meaning: 'the sentence says what they are' },
  { role: 'mentioned', words: 'named in passing', meaning: 'named, with none of the above' },
]

export const ROLE_WORDS: Record<Role, string> = Object.fromEntries(
  ROLE_ORDER.map(({ role, words }) => [role, words]),
) as Record<Role, string>

/** Covering government is these feeds' remit, not something these pages discovered. */
export const STATE_MEDIA: Record<string, string> = {
  KBC: 'state broadcaster',
  'Kenya News': 'government news agency',
}

/** Outlets that named a person less often than this are listed, not broken down. */
export const CARD_MIN = 3

/** The part an outlet most often gives them; ties go to the first stored. */
export function topRole(s: OutletPortrayal): Role {
  let best: Role = 'mentioned'
  let most = -1
  for (const [role, n] of Object.entries(s.roles) as [Role, number][]) {
    if (n > most) {
      best = role
      most = n
    }
  }
  return best
}

/** "Ruto is quoted speaking in 32% of mentions, shown doing something in 30% and named in passing in 20%." */
export function roleSentence(name: string, s: OutletPortrayal, limit = 3): string {
  const total = s.mentions || 1
  const shares = (Object.entries(s.roles) as [Role, number][])
    .filter(([, n]) => n)
    .map(([role, n]) => ({ role, share: n / total }))
    .sort((a, b) => b.share - a.share)
    .slice(0, limit)
  const parts = shares.map(({ role, share }, i) =>
    `${ROLE_WORDS[role]} in ${percent(share)}${i === 0 ? ' of mentions' : ''}`)
  return parts.length ? `${name} is ${listing(parts)}.` : ''
}

/** A few headlines behind the counts: one per role first, then the newest. */
export function personHeadlines(records: readonly MentionRecord[], limit = 6): MentionRecord[] {
  const time = (r: MentionRecord) => parseDate(r.date)?.getTime() ?? 0
  const ordered = [...records].sort((a, b) =>
    Number(a.field !== 'headline') - Number(b.field !== 'headline') || time(b) - time(a))
  const picked: MentionRecord[] = []
  const seen = new Set<string>()
  const take = (record: MentionRecord) => {
    if (!seen.has(record.url) && picked.length < limit) {
      seen.add(record.url)
      picked.push(record)
    }
  }
  for (const { role } of ROLE_ORDER) {
    const first = ordered.find((r) => r.role === role && !seen.has(r.url))
    if (first) take(first)
  }
  for (const record of ordered) take(record)
  return picked.sort((a, b) => time(b) - time(a))
}

/** The title an outlet's headlines most often give them. */
export function usualTitle(s: OutletPortrayal): string {
  const titles = Object.entries(s.titles)
    .filter(([title]) => title !== '(no title)')
    .sort((a, b) => b[1] - a[1])
  if (!titles.length) return ''
  const [title] = titles[0]
  return s.title_forms[title] ?? title
}

/** The title most outlets' headlines give them: 'President', 'DCP leader'. */
export function overallTitle(person: Person): string {
  const totals = new Map<string, number>()
  const forms = new Map<string, string>()
  for (const s of Object.values(person.outlets)) {
    for (const [title, n] of Object.entries(s.titles)) {
      if (title === '(no title)') continue
      totals.set(title, (totals.get(title) ?? 0) + n)
      if (!forms.has(title)) forms.set(title, s.title_forms[title] ?? title)
    }
  }
  const best = [...totals].sort((a, b) => b[1] - a[1])[0]
  return best ? (forms.get(best[0]) ?? best[0]) : ''
}

export interface GlanceFact {
  parts: { text: string; strong?: boolean }[]
}

/** Up to three plain sentences a reader can take in at once. Facts, not findings. */
export function glanceFacts(named: [string, OutletPortrayal][], absent: [string, number][]): GlanceFact[] {
  const facts: GlanceFact[] = []
  const shares = named
    .filter(([, s]) => s.outlet_articles)
    .map(([outlet, s]) => ({ outlet, s, share: s.articles / s.outlet_articles }))
    .sort((a, b) => b.share - a.share)
  if (shares.length) {
    const { outlet, s } = shares[0]
    facts.push({ parts: [
      { text: 'Named most often by ' }, { text: outlet, strong: true },
      { text: `: ${s.articles} of its ${count(s.outlet_articles)} articles.` },
    ] })
  }
  if (absent.length) {
    const names = absent.map(([o]) => o)
    const shown = names.length <= 4 ? names : names.slice(0, 3)
    const parts: GlanceFact['parts'] = [{ text: 'Never named by ' }]
    shown.forEach((name, i) => {
      if (i) parts.push({ text: ', ' })
      parts.push({ text: name, strong: true })
    })
    parts.push({ text: names.length > shown.length ? ` and ${names.length - shown.length} more.` : '.' })
    facts.push({ parts })
  }
  const speaking = named
    .filter(([, s]) => s.articles >= CARD_MIN && s.mentions)
    .map(([outlet, s]) => ({ outlet, share: (s.roles.speaks ?? 0) / s.mentions }))
    .sort((a, b) => b.share - a.share)
  if (speaking.length >= 2) {
    const high = speaking[0]
    const low = speaking[speaking.length - 1]
    if (high.share - low.share >= 0.15) {
      facts.push({ parts: [
        { text: 'Shown speaking most in ' }, { text: high.outlet, strong: true },
        { text: ` (${percent(high.share)} of mentions), least in ` }, { text: low.outlet, strong: true },
        { text: ` (${percent(low.share)}).` },
      ] })
    }
  }
  return facts
}

/** Negative, neutral and positive shares of a tone mix, which sum to one. */
export function toneShares(tone: Tone) {
  const neutral = Math.max(0, 1 - tone.negative - tone.positive)
  return { negative: tone.negative, neutral, positive: tone.positive }
}

/** True when any outlet's tone was read toward the person (NewsMTSC), not the sentence. */
export function toneTargeted(person: Person): boolean {
  return Object.values(person.outlets).some((s) => (s.tone_by ?? []).includes('targeted'))
}
