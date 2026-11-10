// Wording helpers, ported from backend/scripts/build_site.py so the React site and
// the static site say the same things in the same words.

const NUMBER_FORMAT = new Intl.NumberFormat('en-GB')

export function count(n: number): string {
  return NUMBER_FORMAT.format(n)
}

/** "1 story", "3 stories", "1,751 articles". */
export function plural(n: number, word: string, many?: string): string {
  return `${count(n)} ${n === 1 ? word : (many ?? `${word}s`)}`
}

/** "A", "A and B", "A, B and C". */
export function listing(names: readonly string[]): string {
  if (names.length <= 1) return names[0] ?? ''
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

/** "The one fact found was", "1 of the 5 facts was", "4 of the 5 facts were". */
export function someOf(k: number, n: number): string {
  if (n === 1) return 'The one fact found was'
  return `${k} of the ${n} facts ${k === 1 ? 'was' : 'were'}`
}

/**
 * Cut at a sentence end or a word boundary, never mid-word: slicing produced
 * "from 2015 t", and ragged cuts undercut the most trustworthy table on the page.
 */
export function trim(text: string | null | undefined, limit: number): string {
  const clean = (text ?? '').split(/\s+/).filter(Boolean).join(' ')
  if (clean.length <= limit) return clean
  const cut = clean.slice(0, limit)
  for (const stop of ['. ', '? ', '! ']) {
    const at = cut.lastIndexOf(stop)
    if (at > limit * 0.6) return cut.slice(0, at + 1)
  }
  const at = cut.lastIndexOf(' ')
  return `${(at > 0 ? cut.slice(0, at) : cut).replace(/[ ,;:]+$/, '')}…`
}

export function capitalise(text: string): string {
  return text ? text[0].toUpperCase() + text.slice(1) : text
}

/** A date from the API, or a stored "2026-10-22 18:05:23+03:00". */
export function parseDate(value: string | null | undefined): Date | null {
  if (!value) return null
  const date = new Date(value.includes('T') ? value : value.replace(' ', 'T'))
  return Number.isNaN(date.getTime()) ? null : date
}

// Kenyan time for every date: the outlets publish in it and readers live in it.
const ZONE = 'Africa/Nairobi'

/** "27 Oct" */
export function day(value: string | Date | null | undefined): string {
  const date = value instanceof Date ? value : parseDate(value)
  if (!date) return ''
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: ZONE })
}

/** "27 October 2026" */
export function fullDate(value: string | Date | null | undefined): string {
  const date = value instanceof Date ? value : parseDate(value)
  if (!date) return ''
  return date.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: ZONE,
  })
}

/** "21 Aug to 27 Oct 2026" */
export function period(first: string | null, last: string | null): string {
  const end = parseDate(last)
  if (!first || !end) return ''
  return `${day(first)} to ${day(end)} ${end.toLocaleDateString('en-GB', { year: 'numeric', timeZone: ZONE })}`
}

/** 'Nation Africa' -> 'NA', 'The Kenya Times' -> 'KT', 'KBC' -> 'KB'. */
export function initials(outlet: string): string {
  const words = (outlet.match(/[A-Za-z0-9]+/g) ?? []).filter((w) => w.toLowerCase() !== 'the')
  const letters = words.length > 1 ? words.slice(0, 2).map((w) => w[0]).join('') : (words[0] ?? '?').slice(0, 2)
  return letters.toUpperCase()
}

/** 'The Kenya Times' -> 'the-kenya-times': the API's slug for an outlet. */
export function slugOf(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
}

/**
 * The link if it is a web link, otherwise null. Feed links are third-party input:
 * a "javascript:" link would run when clicked, whatever escaping is done (DEF-27).
 */
export function safeUrl(url: string | null | undefined): string | null {
  const clean = (url ?? '').trim()
  return /^https?:\/\/[^\s/]/i.test(clean) ? clean : null
}

const WORDS = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
  'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen',
  'eighteen', 'nineteen', 'twenty']

/** "twelve" for 12; digits above twenty. */
export function numberWord(n: number): string {
  return WORDS[n] ?? count(n)
}

/** 0.217 -> "22%" */
export function percent(share: number): string {
  return `${Math.round(share * 100)}%`
}
