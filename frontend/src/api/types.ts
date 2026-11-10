// The shapes the read-only API returns (backend/api/main.py). Analysis fields are
// passed through from the stored analysis, so they keep the pipeline's names.

export type Iso = string

export interface Differences {
  score: number
  reasons: string[]
}

export interface StorySummary {
  id: number
  headline: string | null
  topic: string | null
  outlets: string[]
  article_count: number | null
  coherence: number | null
  latest: Iso | null
  status: string
  analysed_at: Iso | null
  differences: Differences | null
  facts_not_in_every_outlet: number | null
  numbers_to_compare: number | null
  unread_outlets: string[] | null
  comparable: boolean | null
}

export interface StoryPage {
  total: number
  limit: number
  offset: number
  items: StorySummary[]
}

export interface ContestedStory extends StorySummary {
  contention: { score: number; reasons: string[] }
}

export interface ContestedPage {
  days: number
  until: Iso | null
  items: ContestedStory[]
}

export interface Topic {
  topic: string
  stories: number
}

export interface Readability {
  recorded: boolean
  readable_outlets: string[] | null
  unread_outlets: string[] | null
}

export interface Article {
  id: number
  outlet: string
  title: string
  url: string
  published: Iso | null
  snippet: string | null
  /** false: the article could not be opened; null: not part of the last analysis */
  readable: boolean | null
}

/** One fact, and which outlets reported it, something similar, or nothing. */
export interface FactGroup {
  anchor: { text: string; source?: string }
  reported_by?: string[]
  omitted_by?: string[]
  related?: { source: string; text: string }[]
}

export type QuoteRelation =
  | 'first'
  | 'same'
  | 'says more'
  | 'says less'
  | 'worded differently'
  | 'not compared'

export interface QuoteVersion {
  source: string
  quote: string
  relation: QuoteRelation
  url?: string | null
}

export interface Remark {
  speaker: string | null
  outlets: number
  versions: QuoteVersion[]
}

export interface FramingSource {
  source: string
  frame: string
  score: number
  scored_by?: string
  mentions?: number
  example?: string | null
  example_frame?: string | null
}

export interface FramingRecord {
  entity: string
  sources: FramingSource[]
  spread?: number
}

export interface Figure {
  figure: string | null
  value: number | null
  unit: string | null
  source: string | null
  credited_to: string | null
  cumulative: boolean
  currency: string | null
  breakdown: string[]
  sentence: string
  context: string
  url: string | null
}

export interface FigureGroup {
  unit: string
  sources: string[]
  values: Figure[]
}

export interface Numbers {
  groups: FigureGroup[]
  ungrouped: Figure[]
  solo: Figure[]
}

export interface Analysis {
  coverage: FactGroup[]
  quotes: Remark[]
  figures: unknown[]
  framing: FramingRecord[]
  differences: Differences
  numbers: Numbers
}

export interface NamedPerson {
  id: string
  name: string
}

export interface Story {
  id: number
  headline: string | null
  topic: string | null
  subject: string | null
  coherence: number | null
  article_count: number | null
  outlets: string[]
  clustered_at: Iso | null
  status: string
  analysed_at: Iso | null
  readability: Readability
  articles: Article[]
  analysis: Analysis | null
  people: NamedPerson[]
}

export interface SearchHit {
  id: number
  title: string
  outlet: string
  url: string
  published: Iso | null
  snippet: string | null
  story_id: number | null
  similarity: number
}

export interface SearchResults {
  query: string
  results: SearchHit[]
}

export interface Tone {
  n: number
  negative: number
  positive: number
  label?: string
}

export interface PersonSummary {
  id: string
  name: string
  articles: number
  outlets: number
  built_at: Iso
  title: string | null
  tone: Tone | null
  never_named_by: string[]
}

export type Role = 'speaks' | 'acts' | 'acted on' | 'spoken about' | 'described' | 'mentioned'

export interface MentionRecord {
  url: string
  headline: string
  /** "2026-10-22 18:05:23+03:00": stored with a space, not a T */
  date: string
  role: Role
  field: 'headline' | 'snippet'
}

export interface Voice {
  speaking: { tone: string; verbs: string[] }[]
  acting: string[]
}

export interface OutletPortrayal {
  articles: number
  mentions: number
  outlet_articles: number
  roles: Partial<Record<Role, number>>
  titles: Record<string, number>
  title_forms: Record<string, string>
  tone: Tone | null
  tone_by?: string[]
  records: MentionRecord[]
  records_total?: number
  voice: Voice
}

export interface Person {
  id: string
  name: string
  aliases: string[]
  articles: number
  outlets: Record<string, OutletPortrayal>
  totals: Record<string, number>
  period_first: Iso | null
  period_last: Iso | null
  built_at: Iso
}

export interface SourceSummary {
  slug: string
  name: string
  website: string | null
  note: string | null
  articles: number
  share: number
  first: Iso | null
  latest: Iso | null
  stories: number
  opened: { read: number; unread: number } | null
  topics: { topic: string; articles: number }[]
}

export interface Headline {
  id: number
  title: string
  url: string
  published: Iso | null
  snippet: string | null
  story_id: number | null
}

export interface Source extends SourceSummary {
  recent: Headline[]
  stories_covered: StorySummary[]
}

export type StorySort = 'outlets' | 'differences' | 'latest'
