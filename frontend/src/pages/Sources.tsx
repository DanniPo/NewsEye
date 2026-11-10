import { useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { Link, useLoaderData } from 'react-router'
import type { LoaderFunctionArgs } from 'react-router'

import { api, ApiError } from '../api/client'
import type { SourceSummary } from '../api/types'
import { Avatar, CountUp, ShareBar } from '../components/Bits'
import { ArrowIcon, OutIcon } from '../components/Icons'
import { StoryCard } from '../components/StoryCard'
import { count, day, fullDate, listing, numberWord, percent, period, plural, safeUrl } from '../lib/format'
import { withTransition } from '../lib/motion'
import { ArticleLink } from './StoryPage'

export async function sourcesLoader({ request }: LoaderFunctionArgs) {
  const [sources, topics] = await Promise.all([
    api.sources({ signal: request.signal }),
    api.topics({ signal: request.signal }),
  ])
  return { sources, stories: topics.reduce((sum, t) => sum + t.stories, 0) }
}

/** In how many analysed stories this outlet's article could be opened, in words. */
export function openedText(source: SourceSummary): { text: string; partly: boolean } {
  const opened = source.opened
  if (!opened) return { text: 'Not yet in a story Newseye has compared', partly: false }
  const total = opened.read + opened.unread
  if (total === 1) {
    return opened.read
      ? { text: 'Its article could be opened in the one story compared', partly: false }
      : { text: 'Its article could not be opened in the one story compared (paywall or blocked)', partly: true }
  }
  if (!opened.unread) return { text: `Its articles could be opened in all ${total} stories compared`, partly: false }
  return {
    text: `Its article could be opened in ${opened.read} of ${total} stories compared (paywall or blocked)`,
    partly: true,
  }
}

type Order = 'articles' | 'stories' | 'name'

const ORDERS: { id: Order; label: string }[] = [
  { id: 'articles', label: 'Most articles' },
  { id: 'stories', label: 'Most shared stories' },
  { id: 'name', label: 'A to Z' },
]

function SourceCard({ source, index, most }: { source: SourceSummary; index: number; most: number }) {
  const opened = openedText(source)
  const style = { '--i': index, viewTransitionName: `source-${source.slug}` } as CSSProperties
  return (
    <Link className="srccard" to={`/sources/${source.slug}`} viewTransition style={style}>
      <div className="srchead">
        <Avatar name={source.name} />
        <div>
          <h3 style={{ viewTransitionName: `source-title-${source.slug}` }}>{source.name}</h3>
          {source.note && <span className="note">{source.note}</span>}
        </div>
      </div>
      <dl className="srcfacts">
        <div><dt>Articles</dt><dd>{count(source.articles)}<small>{percent(source.share)} of all</small></dd></div>
        <div><dt>Shared stories</dt><dd>{source.stories}<small>with other outlets</small></dd></div>
        <div><dt>Newest</dt><dd>{day(source.latest) || '—'}<small>article</small></dd></div>
      </dl>
      <ShareBar share={most ? source.articles / most : 0} label={`${count(source.articles)} articles, ${percent(source.share)} of all`} />
      {source.topics.length > 0 && <p className="srctopics">Mostly {listing(source.topics.map((t) => t.topic))}</p>}
      <p className={`opened${opened.partly ? ' part' : ''}`}>{opened.text}</p>
    </Link>
  )
}

export function Sources() {
  const { sources, stories } = useLoaderData<typeof sourcesLoader>()
  const [order, setOrder] = useState<Order>('articles')
  const sorted = useMemo(() => [...sources].sort((a, b) =>
    order === 'name' ? a.name.localeCompare(b.name)
      : order === 'stories' ? b.stories - a.stories || b.articles - a.articles
        : b.articles - a.articles), [sources, order])
  const articles = sources.reduce((sum, s) => sum + s.articles, 0)
  const most = Math.max(0, ...sources.map((s) => s.articles))
  const blocked = sources.filter((s) => s.opened && s.opened.unread > 0)
  const firsts = sources.map((s) => s.first).filter((d): d is string => !!d).sort()
  const lasts = sources.map((s) => s.latest).filter((d): d is string => !!d).sort()
  return (
    <>
      <title>Sources · Newseye</title>
      <section className="intro">
        <h1>Where the news comes from</h1>
        <p>
          Newseye reads the public feeds of {numberWord(sources.length)} Kenyan news outlets every two hours.
          Here is what each has given it so far: how much it published, the topics it covers most, how
          many of its stories other outlets covered too, and how often its articles could be opened to
          compare.
        </p>
        <p className="meta">Counts of what each feed published, not a rating of any outlet.</p>
      </section>
      <div className="stats">
        <div className="stat"><span className="t">Outlets</span><span className="n"><CountUp value={sources.length} /></span><small>public feeds, read every two hours</small></div>
        <div className="stat hi"><span className="t">Articles</span><span className="n"><CountUp value={articles} /></span><small>{period(firsts[0] ?? null, lasts.at(-1) ?? null)}</small></div>
        <div className="stat"><span className="t">Stories to compare</span><span className="n"><CountUp value={stories} /></span><small>each covered by two or more outlets</small></div>
        <div className="stat"><span className="t">Not always opened</span><span className="n"><CountUp value={blocked.length} /></span><small>outlets whose articles could not always be opened; never counted as leaving facts out</small></div>
      </div>
      <div className="colhead">
        <h2>All sources</h2>
        <div className="sorts" role="group" aria-label="Order the sources">
          {ORDERS.map((o) => (
            <button key={o.id} type="button" className={order === o.id ? 'on' : undefined} aria-pressed={order === o.id}
              onClick={() => withTransition(() => setOrder(o.id))}>
              {o.label}
            </button>
          ))}
        </div>
      </div>
      <div className="srcgrid">
        {sorted.map((s, i) => <SourceCard key={s.slug} source={s} index={i} most={most} />)}
      </div>
    </>
  )
}

export async function sourceLoader({ params, request }: LoaderFunctionArgs) {
  const slug = params.slug ?? ''
  if (!/^[a-z0-9-]{1,60}$/.test(slug)) throw new ApiError(404, 'No such source')
  return api.source(slug, { signal: request.signal })
}

export function SourcePage() {
  const source = useLoaderData<typeof sourceLoader>()
  const opened = openedText(source)
  const website = safeUrl(source.website)
  const host = website ? new URL(website).host.replace(/^www\./, '') : ''
  // the largest topic fills the bar; the counts beside each bar give the scale
  const largest = Math.max(0, ...source.topics.map((t) => t.articles))
  return (
    <>
      <title>{`${source.name} · Sources · Newseye`}</title>
      <div className="crumb"><Link to="/sources" viewTransition>Sources</Link><span>/</span><span>{source.name}</span></div>
      <div className="phead">
        <div>
          <h1 style={{ viewTransitionName: `source-title-${source.slug}` }}>{source.name}</h1>
          <p className="pmeta">
            {source.note && <span className="kpill">{source.note}</span>}
            {plural(source.articles, 'article')} since {fullDate(source.first)} · newest {fullDate(source.latest)}
          </p>
        </div>
        {website && (
          <a className="btn line" href={website} target="_blank" rel="noopener noreferrer">
            Visit {host} <OutIcon />
          </a>
        )}
      </div>
      <div className="stats three">
        <div className="stat"><span className="t">Articles</span><span className="n"><CountUp value={source.articles} /></span><small>{percent(source.share)} of everything Newseye has read</small></div>
        <div className="stat hi"><span className="t">Shared stories</span><span className="n"><CountUp value={source.stories} /></span><small>stories other outlets covered too</small></div>
        <div className="stat"><span className="t">Articles opened</span><span className="s">{source.opened ? `${source.opened.read} of ${source.opened.read + source.opened.unread}` : '—'}</span><small>{opened.text}</small></div>
      </div>
      <div className="story">
        <section className="card">
          <h2>Stories it covered</h2>
          <p className="hint">Its newest stories that other outlets covered too. Open one to compare.</p>
          {source.stories_covered.length ? (
            <div className="grid">
              {source.stories_covered.map((s, i) => <StoryCard key={s.id} story={s} index={i} />)}
            </div>
          ) : (
            <p className="empty">No story yet that another outlet covered too.</p>
          )}
          {source.stories > source.stories_covered.length && (
            <Link className="more" to={`/?source=${source.slug}`} viewTransition>
              See all {source.stories} stories it covered <ArrowIcon />
            </Link>
          )}
        </section>
        <aside className="side">
          <div className="panel">
            <h4>What it covers</h4>
            <p className="sub">Its articles by topic</p>
            <ul className="tbars">
              {source.topics.map((t, i) => (
                <li key={t.topic} style={{ '--i': i } as CSSProperties}>
                  <span>{t.topic === 'General' ? 'No clear topic' : t.topic}</span>
                  <span className="bar"><i style={{ width: `${largest ? (t.articles / largest) * 100 : 0}%` }} /></span>
                  <span className="num">{count(t.articles)}</span>
                </li>
              ))}
            </ul>
            <p className="fine">Topics are read automatically from each headline and opening line; below a confidence of 0.75 an article is left without one.</p>
          </div>
        </aside>
      </div>
      <section className="card">
        <h2>Latest headlines</h2>
        <p className="hint">The newest articles from its feed. Each opens on {source.name}’s own site.</p>
        <ul className="heads">
          {source.recent.map((h) => (
            <li key={h.id}>
              <div>
                <span className="hsrc">{day(h.published)}</span>
                {h.story_id !== null && <Link className="instory" to={`/stories/${h.story_id}`} viewTransition>compare</Link>}
              </div>
              <ArticleLink url={h.url}>{h.title}</ArticleLink>
            </li>
          ))}
        </ul>
      </section>
      <footer className="end">
        Counts describe what {source.name}’s feed published while Newseye was reading it, not everything the
        outlet published, and say nothing about its accuracy.
      </footer>
    </>
  )
}
