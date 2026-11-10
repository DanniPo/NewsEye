// Answers shaped like the real API's, from a real story (1387) and real outlets,
// shortened. One article link is a "javascript:" link on purpose (DEF-27).

import type {
  ContestedPage,
  Figure,
  Person,
  PersonSummary,
  SearchResults,
  Source,
  SourceSummary,
  Story,
  StoryPage,
  StorySummary,
  Topic,
} from '../api/types'

export const NOW = '2026-10-27T16:30:00+03:00'

export const CARD: StorySummary = {
  id: 1387,
  headline: 'Kenya Warns Nigeria Over Treatment of Kenyans Seeking Visas',
  topic: 'International',
  outlets: ['Capital FM', 'People Daily', 'The Kenya Times'],
  article_count: 3,
  coherence: 0.71,
  latest: NOW,
  status: 'analysed',
  analysed_at: NOW,
  differences: { score: 2, reasons: ['outlets worded 1 fact differently', 'tone about Nigeria differs between outlets'] },
  facts_not_in_every_outlet: 2,
  numbers_to_compare: 2,
  unread_outlets: ['People Daily'],
  comparable: true,
}

export const CARD_ONE_READABLE: StorySummary = {
  ...CARD,
  id: 1402,
  headline: 'DCI arrests 56 people in Homa Bay crackdown on political goonism',
  topic: null,
  outlets: ['Nairobi Wire', 'People Daily'],
  differences: { score: 0, reasons: [] },
  facts_not_in_every_outlet: 1,
  numbers_to_compare: 0,
  unread_outlets: ['People Daily'],
  comparable: false,
}

export const CARD_WAITING: StorySummary = {
  ...CARD,
  id: 1410,
  headline: 'Makadara ABC church expels choir leaders over misuse of church funds',
  outlets: ['K24 Digital', 'People Daily'],
  status: 'not analysed',
  analysed_at: null,
  differences: null,
  facts_not_in_every_outlet: null,
  numbers_to_compare: null,
  unread_outlets: null,
  comparable: null,
}

export const PAGE: StoryPage = { total: 14, limit: 12, offset: 0, items: [CARD, CARD_ONE_READABLE, CARD_WAITING] }

export const TOPICS: Topic[] = [
  { topic: 'General', stories: 5 },
  { topic: 'Politics', stories: 6 },
  { topic: 'International', stories: 3 },
]

export const SOURCES: SourceSummary[] = [
  {
    slug: 'k24-digital', name: 'K24 Digital', website: 'https://k24.digital', note: null,
    articles: 1751, share: 0.2169, first: '2026-08-27T08:43:43+03:00', latest: NOW, stories: 9,
    opened: { read: 0, unread: 6 }, topics: [{ topic: 'Sports', articles: 180 }, { topic: 'Entertainment', articles: 90 }],
  },
  {
    slug: 'capital-fm', name: 'Capital FM', website: 'https://www.capitalfm.co.ke', note: null,
    articles: 609, share: 0.0754, first: '2026-08-21T09:00:00+03:00', latest: NOW, stories: 15,
    opened: { read: 11, unread: 0 }, topics: [{ topic: 'Politics', articles: 200 }],
  },
  {
    slug: 'kbc', name: 'KBC', website: 'https://www.kbc.co.ke', note: 'state broadcaster',
    articles: 474, share: 0.0587, first: '2026-08-21T09:00:00+03:00', latest: '2026-10-22T10:00:00+03:00', stories: 7,
    opened: { read: 3, unread: 2 }, topics: [{ topic: 'Politics', articles: 120 }],
  },
  {
    slug: 'the-sharp-daily', name: 'The Sharp Daily', website: 'https://thesharpdaily.com', note: null,
    articles: 105, share: 0.013, first: '2026-08-30T09:00:00+03:00', latest: NOW, stories: 5,
    opened: { read: 1, unread: 0 }, topics: [{ topic: 'Business', articles: 30 }],
  },
  {
    slug: 'amref-newsroom', name: 'Amref Newsroom', website: 'https://newsroom.amref.org', note: null,
    articles: 46, share: 0.0057, first: '2026-09-01T09:00:00+03:00', latest: '2026-10-26T09:00:00+03:00', stories: 0,
    opened: null, topics: [{ topic: 'Health', articles: 20 }],
  },
]

export const SOURCE: Source = {
  ...SOURCES[1],
  topics: [{ topic: 'General', articles: 300 }, { topic: 'Politics', articles: 200 }, { topic: 'Health', articles: 40 }],
  recent: [
    { id: 11, title: "Kenya protests 'unacceptable' treatment of citizens seeking Nigerian visas", url: 'https://www.capitalfm.co.ke/news/a', published: NOW, snippet: 'NAIROBI', story_id: 1387 },
    { id: 12, title: 'Harambee Stars name squad for qualifier', url: 'https://www.capitalfm.co.ke/sports/b', published: NOW, snippet: null, story_id: null },
  ],
  stories_covered: [CARD],
}

function figure(text: string, source: string, sentence: string, extra: Partial<Figure> = {}): Figure {
  return {
    figure: text, value: null, unit: 'months', source, credited_to: null, cumulative: false, currency: 'unspecified',
    breakdown: [], sentence, context: sentence, url: 'https://www.capitalfm.co.ke/news/a', ...extra,
  }
}

export const STORY: Story = {
  id: 1387,
  headline: CARD.headline,
  topic: 'International',
  subject: null,
  coherence: 0.71,
  article_count: 3,
  outlets: ['Capital FM', 'People Daily', 'The Kenya Times'],
  clustered_at: NOW,
  status: 'analysed',
  analysed_at: NOW,
  readability: { recorded: true, readable_outlets: ['Capital FM', 'The Kenya Times'], unread_outlets: ['People Daily'] },
  articles: [
    { id: 1, outlet: 'Capital FM', title: "Kenya protests 'unacceptable' treatment of citizens seeking Nigerian visas", url: 'https://www.capitalfm.co.ke/news/a', published: '2026-10-27T10:00:00+03:00', snippet: 'NAIROBI, Kenya', readable: true },
    { id: 2, outlet: 'People Daily', title: "PS Korir Sing'Oei raises concern over treatment of Kenyans seeking Nigerian visas", url: 'https://peopledaily.digital/b', published: '2026-10-27T11:00:00+03:00', snippet: null, readable: false },
    { id: 3, outlet: 'The Kenya Times', title: 'Kenya Warns Nigeria Over Treatment of Kenyans Seeking Visas', url: 'javascript:alert(1)', published: '2026-10-27T12:00:00+03:00', snippet: null, readable: true },
  ],
  analysis: {
    coverage: [
      {
        anchor: { text: 'Kenya has protested the treatment of its citizens applying for visas to Nigeria.' },
        reported_by: ['Capital FM'], omitted_by: [],
        related: [{ source: 'The Kenya Times', text: 'Kenya warned Nigeria over the treatment of Kenyans seeking visas.' }],
      },
      {
        anchor: { text: "The applicant's passport must have at least six months' validity and blank pages." },
        reported_by: ['Capital FM'], omitted_by: ['The Kenya Times'], related: [],
      },
    ],
    quotes: [
      {
        speaker: 'Korir Sing’Oei', outlets: 2,
        versions: [
          { source: 'Capital FM', quote: 'This treatment is unacceptable and must stop', relation: 'first' },
          { source: 'The Kenya Times', quote: 'This treatment of our citizens is unacceptable and must stop', relation: 'says more' },
        ],
      },
      { speaker: 'Musalia Mudavadi', outlets: 1, versions: [{ source: 'Capital FM', quote: 'We are engaging our Nigerian counterparts', relation: 'first' }] },
    ],
    figures: [],
    framing: [{
      entity: 'Nigeria',
      sources: [
        { source: 'Capital FM', frame: 'negative', score: -0.4, scored_by: 'sentence', mentions: 2, example: 'Nigeria was accused of mistreating applicants.', example_frame: 'negative' },
        { source: 'The Kenya Times', frame: 'neutral', score: 0, scored_by: 'sentence', mentions: 1, example: 'Kenya wrote to Nigeria.', example_frame: 'neutral' },
      ],
    }],
    differences: { score: 2, reasons: ['outlets worded 1 fact differently', 'tone about Nigeria differs between outlets'] },
    numbers: {
      groups: [{
        unit: 'months', sources: ['Capital FM', 'The Kenya Times'],
        values: [
          figure('six months', 'Capital FM', "The passport must have six months' validity, the ministry said."),
          figure('6 months', 'The Kenya Times', 'Passports need 6 months of validity.'),
        ],
      }],
      ungrouped: [],
      solo: [figure('90 days', 'Capital FM', 'Visas are issued within 90 days.', { unit: 'days', credited_to: 'ministry' })],
    },
  },
  people: [{ id: 'musalia-mudavadi', name: 'Musalia Mudavadi' }],
}

export const CONTESTED: ContestedPage = {
  days: 7,
  until: NOW,
  items: [{ ...CARD, contention: { score: 1.25, reasons: ['2 of 3 headlines report a dispute', 'International'] } }],
}

export const PEOPLE: PersonSummary[] = [
  { id: 'william-ruto', name: 'William Ruto', articles: 605, outlets: 10, built_at: NOW, title: 'President', tone: { n: 400, negative: 0.2, positive: 0.35 }, never_named_by: ['The Sharp Daily', 'Amref Newsroom'] },
  { id: 'raila-odinga', name: 'Raila Odinga', articles: 252, outlets: 9, built_at: NOW, title: null, tone: null, never_named_by: [] },
]

export const PERSON: Person = {
  id: 'william-ruto',
  name: 'William Ruto',
  aliases: ['Ruto', 'President Ruto'],
  articles: 605,
  period_first: '2026-08-21T09:00:00+03:00',
  period_last: NOW,
  built_at: NOW,
  totals: { 'Capital FM': 609, KBC: 474, 'The Sharp Daily': 105 },
  outlets: {
    'Capital FM': {
      articles: 72, mentions: 80, outlet_articles: 609,
      roles: { speaks: 40, acts: 24, mentioned: 16 },
      titles: { president: 50, '(no title)': 30 }, title_forms: { president: 'President' },
      tone: { n: 110, negative: 0.1, positive: 0.4, label: 'leans positive' }, tone_by: ['targeted'],
      records: [
        { url: 'https://www.capitalfm.co.ke/r1', headline: 'Ruto says housing levy will stay', date: '2026-10-22 18:05:23+03:00', role: 'speaks', field: 'headline' },
        { url: 'https://www.capitalfm.co.ke/r2', headline: 'Ruto tours Kisumu', date: '2026-10-20 09:00:00+03:00', role: 'acts', field: 'headline' },
      ],
      voice: { speaking: [{ tone: 'neutral', verbs: ['says'] }, { tone: 'critical', verbs: ['accuses'] }], acting: [] },
    },
    KBC: {
      articles: 44, mentions: 50, outlet_articles: 474,
      roles: { acts: 30, speaks: 5, mentioned: 15 },
      titles: { president: 40 }, title_forms: { president: 'President' },
      tone: { n: 70, negative: 0, positive: 0.6 }, tone_by: ['targeted'],
      records: [{ url: 'https://www.kbc.co.ke/r3', headline: 'President Ruto opens market', date: '2026-10-21 08:00:00+03:00', role: 'acts', field: 'headline' }],
      voice: { speaking: [], acting: ['opens', 'tours'] },
    },
  },
}

export const RESULTS: SearchResults = {
  query: 'housing levy',
  results: [
    { id: 21, title: 'Ruto defends housing levy', outlet: 'Capital FM', url: 'https://www.capitalfm.co.ke/c', published: NOW, snippet: 'President William Ruto has defended the housing levy', story_id: 1387, similarity: 0.61 },
    { id: 22, title: 'Levy row in Senate', outlet: 'KBC', url: 'data:text/html,hi', published: NOW, snippet: null, story_id: null, similarity: 0.44 },
  ],
}
