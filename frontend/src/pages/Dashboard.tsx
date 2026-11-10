import { useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { Link, useLoaderData, useLocation, useNavigate } from 'react-router'
import type { LoaderFunctionArgs } from 'react-router'

import { api } from '../api/client'
import type { PersonSummary, SourceSummary, StoryPage, StorySort, StorySummary, Topic } from '../api/types'
import { Avatar, CountUp } from '../components/Bits'
import { ArrowIcon, CloseIcon } from '../components/Icons'
import { StoryCard } from '../components/StoryCard'
import { day, listing, numberWord, plural, trim } from '../lib/format'
import { useIntroCycle } from '../lib/motion'

/** stories per page of the list; "Show more" adds the next page */
export const PAGE = 12

const SORTS: { id: StorySort; label: string }[] = [
  { id: 'outlets', label: 'Most outlets' },
  { id: 'differences', label: 'Most differences' },
  { id: 'latest', label: 'Latest' },
]

function asSort(value: string | null): StorySort {
  return value === 'differences' || value === 'latest' ? value : 'outlets'
}

export async function dashboardLoader({ request }: LoaderFunctionArgs) {
  const params = new URL(request.url).searchParams
  const sort = asSort(params.get('sort'))
  const topic = params.get('topic') || null
  const source = params.get('source') || null
  const signal = request.signal
  const [stories, topics, sources, latest, people] = await Promise.all([
    api.stories({ limit: PAGE, sort, topic, source }, { signal }),
    api.topics({ signal }),
    api.sources({ signal }),
    // the side panels are extras: the page stands without them
    api.stories({ limit: 4, sort: 'latest' }, { signal }).catch(() => null),
    api.people({ signal }).catch(() => null),
  ])
  return { stories, topics, sources, latest, people, sort, topic, source }
}

type Data = Awaited<ReturnType<typeof dashboardLoader>>

/**
 * The opening: what Newseye is for, in one line. The outlet names run through
 * once as the page opens, then the line settles on its static wording.
 */
function Hero({ sources }: { sources: SourceSummary[] }) {
  const names = useMemo(() => sources.filter((s) => s.articles > 0).map((s) => s.name), [sources])
  const current = useIntroCycle(names)
  return (
    <section className="intro hero">
      <p className="eyebrow">Kenyan news, side by side</p>
      <h1>
        One story, <span className="hl">{numberWord(sources.length)} newsrooms</span>.{' '}
        <span className="nowrap">See how{' '}
          {current ? (
            <>
              <span className="rot" aria-hidden="true"><span key={current} className="rot-in">{current}</span></span>
              <span className="sr-only">each one</span>
            </>
          ) : (
            <span className="rot-end">each one</span>
          )}
        </span>{' '}tells it.
      </h1>
      <p>
        Newseye reads {sources.length} Kenyan news sites, groups the articles about each event and
        lays them side by side: what each outlet reported, who it quoted and which numbers it gave.
        It does not say who is right. You compare.
      </p>
      <ol className="steps">
        <li>Pick a story</li>
        <li>See what each outlet reported, side by side</li>
        <li>Open the original articles</li>
      </ol>
    </section>
  )
}

/** The place where the sources are shown: every outlet, one click from its page. */
function SourcesCard({ sources }: { sources: SourceSummary[] }) {
  const articles = sources.reduce((sum, s) => sum + s.articles, 0)
  const newest = sources.map((s) => s.latest).filter(Boolean).sort().at(-1) ?? null
  return (
    <section className="stat wide sourcescard" aria-labelledby="our-sources">
      <div className="cardhead">
        <h2 className="k" id="our-sources">Our sources</h2>
        <Link className="more" to="/sources" viewTransition>
          All {sources.length} sources <ArrowIcon />
        </Link>
      </div>
      <ul className="srcchips">
        {sources.map((s, i) => (
          <li key={s.slug} style={{ '--i': i } as CSSProperties}>
            <Link to={`/sources/${s.slug}`} viewTransition title={`${s.name}: ${plural(s.articles, 'article')}`}>
              <Avatar name={s.name} />
              <span>{s.name}</span>
            </Link>
          </li>
        ))}
      </ul>
      <small>{plural(articles, 'article')} read from their public feeds{newest ? ` · newest ${day(newest)}` : ''}</small>
    </section>
  )
}

function Counts({ sources, total }: { sources: SourceSummary[]; total: number }) {
  return (
    <div className="stats">
      <div className="stat">
        <span className="t">Outlets read</span>
        <span className="n"><CountUp value={sources.length} /></span>
        <small>Kenyan news sites, through their public feeds</small>
      </div>
      <div className="stat hi">
        <span className="t">Stories to compare</span>
        <span className="n"><CountUp value={total} /></span>
        <small>each covered by two or more outlets</small>
      </div>
      <SourcesCard sources={sources} />
    </div>
  )
}

function useQuery() {
  const location = useLocation()
  const navigate = useNavigate()
  const params = new URLSearchParams(location.search)
  /** change the list in place: the cards glide to their new places */
  const set = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(location.search)
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    const search = next.toString()
    void navigate({ search: search ? `?${search}` : '' }, { preventScrollReset: true, viewTransition: true })
  }
  return { params, set }
}

function Categories({ topics, active, total }: { topics: Topic[]; active: string | null; total: number }) {
  const { set } = useQuery()
  if (topics.length < 2) return null
  // "General" is the label for no clear topic, so it comes last whatever its count
  const ordered = [...topics].sort((a, b) =>
    Number(a.topic === 'General') - Number(b.topic === 'General') || b.stories - a.stories || a.topic.localeCompare(b.topic))
  const button = (topic: string | null, name: string, n: number) => (
    <button key={name} type="button" className={active === topic ? 'on' : undefined}
      aria-pressed={active === topic} onClick={() => set({ topic })}>
      <b>{name}</b>
      <small>{plural(n, 'story', 'stories')}</small>
    </button>
  )
  return (
    <section className="catblock" aria-labelledby="browse">
      <div className="colhead"><h2 id="browse">Browse by category</h2></div>
      <p className="under">Pick a category to show only its stories.</p>
      <div className="cats" role="group" aria-label="News categories">
        {button(null, 'All stories', total)}
        {ordered.map((t) => button(t.topic, t.topic, t.stories))}
      </div>
    </section>
  )
}

function StoryList({ data }: { data: Data }) {
  const { set } = useQuery()
  const location = useLocation()
  // stories added by "Show more" belong to the list they were loaded for; a new
  // filter or order starts again, while the cards already shown stay mounted, so
  // they glide to their new places instead of being drawn afresh
  const [added, setAdded] = useState<{ search: string; items: StorySummary[] }>({ search: location.search, items: [] })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<{ search: string; text: string } | null>(null)
  const page: StoryPage = data.stories
  const extra = added.search === location.search ? added.items : []
  const items = [...page.items, ...extra]
  const sourceName = data.source ? data.sources.find((s) => s.slug === data.source)?.name ?? data.source : null

  const more = () => {
    const search = location.search
    setLoading(true)
    setError(null)
    api.stories({ limit: PAGE, offset: items.length, sort: data.sort, topic: data.topic, source: data.source })
      .then((next) => setAdded({ search, items: [...extra, ...next.items] }))
      .catch((err: Error) => setError({ search, text: err.message }))
      .finally(() => setLoading(false))
  }

  return (
    <div>
      <div className="colhead" id="stories">
        <h2>Stories to compare</h2>
        <span className="hint" aria-live="polite">{plural(page.total, 'story', 'stories')}</span>
      </div>
      <p className="under">Open a story to see what each outlet reported, side by side.</p>
      {sourceName && (
        <p className="filterchip">
          <span>Covered by <b>{sourceName}</b></span>
          <button type="button" onClick={() => set({ source: null })} aria-label={`Show stories from every outlet, not only ${sourceName}`}>
            <CloseIcon />
          </button>
        </p>
      )}
      <div className="sorts" role="group" aria-label="Order the stories">
        {SORTS.map((s) => (
          <button key={s.id} type="button" className={data.sort === s.id ? 'on' : undefined}
            aria-pressed={data.sort === s.id} onClick={() => set({ sort: s.id === 'outlets' ? null : s.id })}>
            {s.label}
          </button>
        ))}
      </div>
      {items.length ? (
        <div className="grid">
          {items.map((story, i) => <StoryCard key={story.id} story={story} index={i} />)}
        </div>
      ) : (
        <div className="empty-grid">No story matches that. Try another category, or search every article.</div>
      )}
      {items.length < page.total && (
        <div className="moreline">
          <button type="button" className="btn line" onClick={more} disabled={loading}>
            {loading ? 'Loading…' : `Show more stories (${page.total - items.length} left)`}
          </button>
          {error && error.search === location.search && <p className="hint" role="alert">{error.text}</p>}
        </div>
      )}
    </div>
  )
}

function LatestPanel({ stories }: { stories: StorySummary[] }) {
  if (!stories.length) return null
  return (
    <div className="panel">
      <h4>Latest stories</h4>
      <p className="sub">By their newest article</p>
      <ul className="latest">
        {stories.map((s) => (
          <li key={s.id}>
            <Link to={`/stories/${s.id}`} viewTransition>
              <span>
                <b>{trim(s.headline ?? 'Untitled story', 72)}</b>
                <small>{plural(s.article_count ?? 0, 'article')} · {plural(s.outlets.length, 'outlet')}</small>
              </span>
              <time dateTime={s.latest ?? undefined}>{day(s.latest)}</time>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}

function PeoplePanel({ people }: { people: PersonSummary[] }) {
  if (!people.length) return null
  return (
    <div className="panel">
      <h4>People in the news</h4>
      <p className="sub">Named most often across the outlets</p>
      <div className="rank">
        {people.slice(0, 6).map((p, i) => (
          <div className="r" key={p.id}>
            <b>{i + 1}</b>
            <div>
              <Link to={`/people/${p.id}`} viewTransition><span>{p.name}</span></Link>
              <small>{p.articles} articles · {p.outlets} outlets</small>
            </div>
          </div>
        ))}
      </div>
      <Link className="more" to="/people" viewTransition>How each outlet presents them <ArrowIcon /></Link>
    </div>
  )
}

/** The caveats a reader needs once, folded until they ask. */
function About({ sources }: { sources: SourceSummary[] }) {
  const location = useLocation()
  const box = useRef<HTMLDetailsElement>(null)
  useEffect(() => {
    if (location.hash === '#about' && box.current) {
      box.current.open = true
      box.current.scrollIntoView({ block: 'start' })
    }
  }, [location.hash, location.key])
  const blocked = sources.filter((s) => s.opened && s.opened.unread > 0).map((s) => s.name)
  return (
    <details className="howto" id="about" ref={box}>
      <summary>How it works</summary>
      <div className="pbody">
        <p><b>Not reported is not wrong.</b> An outlet may leave a fact out because it ran a shorter piece or filed earlier. The gap shows what you would miss by reading only that outlet.</p>
        {blocked.length > 0 && (
          <p><b>Some sites could not always be opened</b> (paywall or blocked): {listing(blocked)}. They are never counted as leaving something out.</p>
        )}
        <p><b>What it does not do.</b> It does not rate outlets, decide which number is right, or call anything false. Where two numbers are too far apart to be the same thing, both are shown with their sentences.</p>
        <p><b>Where it comes from.</b> Headlines and opening lines from each outlet’s public feed, checked every two hours; the article text is read once and not kept.</p>
      </div>
    </details>
  )
}

export function Dashboard() {
  const data = useLoaderData<typeof dashboardLoader>()
  const total = data.topics.reduce((sum, t) => sum + t.stories, 0)
  return (
    <>
      <title>Newseye: Kenyan news compared</title>
      <Hero sources={data.sources} />
      <Counts sources={data.sources} total={total} />
      <Categories topics={data.topics} active={data.topic} total={total} />
      <div className="cols">
        <StoryList data={data} />
        <div>
          <LatestPanel stories={data.latest?.items ?? []} />
          <PeoplePanel people={data.people ?? []} />
          <About sources={data.sources} />
        </div>
      </div>
    </>
  )
}
