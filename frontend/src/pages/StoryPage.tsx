import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { Link, useLoaderData, useLocation, useNavigate } from 'react-router'
import type { LoaderFunctionArgs } from 'react-router'

import { api, ApiError } from '../api/client'
import type { Article, FactGroup, Figure, Numbers, Remark, Story } from '../api/types'
import { Avatar } from '../components/Bits'
import { OutIcon } from '../components/Icons'
import { Tabs } from '../components/Tabs'
import type { TabItem } from '../components/Tabs'
import { day, listing, plural, safeUrl, slugOf, trim } from '../lib/format'
import { usePrefersReducedMotion } from '../lib/motion'
import {
  coverageRows,
  figureInContext,
  figureTags,
  firstArticles,
  framingRows,
  gapsIn,
  glancePoints,
  markAdded,
  QUOTE_RELATION,
  readOutlets,
  SHOWN_REMARKS,
  splitRemarks,
} from '../lib/story'
import type { Outlets, TabId } from '../lib/story'

export async function storyLoader({ params, request }: LoaderFunctionArgs) {
  const id = Number(params.id)
  if (!Number.isInteger(id) || id < 1) throw new ApiError(404, 'No such story')
  const [story, sources] = await Promise.all([
    api.story(id, { signal: request.signal }),
    api.sources({ signal: request.signal }).catch(() => []),
  ])
  return { story, known: sources.map((s) => s.name) }
}

/** An article's headline as a link to the original, or as text if the link is unsafe. */
export function ArticleLink({ url, children }: { url: string | null | undefined; children: ReactNode }) {
  const href = safeUrl(url)
  if (!href) return <span>{children}</span>
  return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
}

/** An outlet's name, linking to its source page when Newseye reads it. */
function OutletName({ name, known }: { name: string; known: Set<string> }) {
  if (!known.has(name)) return <>{name}</>
  return <Link to={`/sources/${slugOf(name)}`} viewTransition className="olink">{name}</Link>
}

function tabsFor(story: Story): TabItem<TabId>[] {
  const tabs: TabItem<TabId>[] = [{ id: 'overview', label: 'Overview' }]
  const analysis = story.analysis
  if (!analysis) return tabs
  tabs.push({ id: 'facts', label: 'Facts', count: analysis.coverage.length })
  if (analysis.quotes.length) tabs.push({ id: 'quotes', label: 'Quotes', count: analysis.quotes.length })
  if (framingRows(analysis.framing).rows.length) tabs.push({ id: 'tone', label: 'Tone' })
  const n = analysis.numbers
  tabs.push({ id: 'numbers', label: 'Numbers', count: n.groups.reduce((s, g) => s + g.values.length, 0) + n.ungrouped.length + n.solo.length })
  return tabs
}

function Glance({ story, onTab }: { story: Story; onTab: (id: TabId) => void }) {
  return (
    <div className="atglance">
      <b className="t">At a glance</b>
      <ul>
        {glancePoints(story).map((point) => (
          <li key={point.text}>
            {point.text}
            {point.link && (
              <> <button type="button" className="linkish" onClick={() => onTab(point.link!.tab)}>{point.link.label}</button></>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

function Headlines({ articles, known }: { articles: Article[]; known: Set<string> }) {
  return (
    <div className="heads-block" id="headlines">
      <h3 className="sub">Headlines</h3>
      <p className="hint">Each outlet’s own headline, linking to its article.</p>
      <ul className="heads">
        {articles.map((a) => (
          <li key={a.id}>
            <div>
              <span className="hsrc"><OutletName name={a.outlet} known={known} />
                {a.readable === false && <span className="unread">could not open</span>}
              </span>
            </div>
            <ArticleLink url={a.url}>{a.title}</ArticleLink>
          </li>
        ))}
      </ul>
    </div>
  )
}

const CELL = {
  reported: { mark: '✓', css: 'y', words: 'reported this' },
  similar: { mark: '≈', css: 'r', words: 'reported something similar' },
  'not reported': { mark: '—', css: 'n', words: 'did not report this' },
} as const

function CoverageTable({ coverage, outlets }: { coverage: FactGroup[]; outlets: Outlets }) {
  const { read, unread, recorded } = outlets
  if (!coverage.length || !read.length) {
    return <p className="empty">No fact was reported by more than one outlet we could open.</p>
  }
  const { rows, carried, total } = coverageRows(coverage, read)
  const one = unread.length === 1
  return (
    <>
      <div className="legend">
        <span><i className="y">✓</i> reported it</span>
        <span><i className="r">≈</i> reported something similar</span>
        <span><i className="n">—</i> did not report it</span>
      </div>
      {unread.length > 0 && (
        <p className="hint">
          Not in the table: {listing(unread)}. We could not open {one ? 'its article' : 'their articles'} (paywall
          or blocked), so we cannot say what {one ? 'it' : 'they'} reported.
        </p>
      )}
      {!recorded && (
        <p className="hint">
          This comparison was stored before Newseye recorded which articles it could open, so a dash may
          mean an article that could not be opened.
        </p>
      )}
      <p className="swipe">Swipe the table sideways to see every outlet →</p>
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">What was reported</th>
              {read.map((o) => <th scope="col" key={o}>{o}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="frow" style={{ '--i': i } as CSSProperties}>
                <td className="f">
                  {row.text}
                  <span className="st">{row.status}</span>
                  {row.related.length > 0 && (
                    <details className="rel">
                      <summary>≈ what {listing(row.related.map((r) => r.source))} said instead</summary>
                      {row.related.map((r) => <p key={r.source}><b>{r.source}:</b> {r.text}</p>)}
                    </details>
                  )}
                </td>
                {read.map((o) => {
                  const cell = CELL[row.cells[o]]
                  return (
                    <td key={o} className={`m ${cell.css}`} title={cell.words}>
                      <span aria-hidden="true">{cell.mark}</span>
                      <span className="sr-only">{o} {cell.words}</span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td>Reported</td>
              {read.map((o) => <td key={o}>{carried[o]} of {total}</td>)}
            </tr>
          </tfoot>
        </table>
      </div>
    </>
  )
}

function RemarkCard({ remark }: { remark: Remark }) {
  const first = remark.versions[0]
  return (
    <div className="remark">
      <div className="rhead">
        <b>{remark.speaker || 'Unattributed'}</b>
        <span>quoted by {remark.outlets} outlets</span>
      </div>
      {remark.versions.map((v, i) => {
        const quote = trim(v.quote, 320)
        const relation = QUOTE_RELATION[v.relation] ?? QUOTE_RELATION['not compared']
        return (
          <div className="ver" key={`${v.source}-${i}`}>
            <span className="vsrc">{v.source}</span>
            <div>
              <blockquote>
                “{v.relation === 'says more' && first
                  ? markAdded(quote, first.quote).map((w, j) => (
                    <Fragment key={j}>{j > 0 && ' '}{w.added ? <mark>{w.word}</mark> : w.word}</Fragment>))
                  : quote}”
              </blockquote>
              {i > 0 && <span className={`vrel ${relation.tone}`}>{relation.label}</span>}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function Quotes({ remarks }: { remarks: Remark[] }) {
  const { shared, single } = splitRemarks(remarks)
  const hidden = shared.slice(SHOWN_REMARKS)
  const people = new Set(single.map((r) => r.speaker).filter(Boolean)).size
  return (
    <>
      <h2>What was said</h2>
      {shared.length > 0 && (
        <p className="hint">The same remark as each outlet printed it. Highlighted words are ones the first outlet left out.</p>
      )}
      {shared.slice(0, SHOWN_REMARKS).map((r, i) => <RemarkCard key={i} remark={r} />)}
      {hidden.length > 0 && (
        <details className="pdet">
          <summary><b>More remarks</b><span>{plural(hidden.length, 'other remark')} quoted by several outlets</span></summary>
          <div className="pbody">{hidden.map((r, i) => <RemarkCard key={i} remark={r} />)}</div>
        </details>
      )}
      {single.length > 0 && (
        <details className="pdet" open={!shared.length}>
          <summary><b>Other quotes</b><span>{single.length} from {people} people, each in one outlet</span></summary>
          <ul className="qlist">
            {single.map((r, i) => (
              <li key={i}>
                <b>{r.speaker || 'Unattributed'}</b> · {r.versions[0]?.source}
                <span>“{trim(r.versions[0]?.quote, 220)}”</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  )
}

function ToneSection({ story }: { story: Story }) {
  const { rows, targeted } = framingRows(story.analysis?.framing ?? [])
  return (
    <>
      <h2>How they were described</h2>
      <p className="hint">
        {targeted
          ? 'For a person, each outlet’s overall attitude toward them across its sentences, read by NewsMTSC, a model trained on news; for a place or organisation, the tone of the sentences naming it.'
          : 'The overall tone of each outlet’s sentences naming them, which follows the events as much as the name.'}{' '}
        A hint, not a verdict: it can be wrong.
      </p>
      {rows.map((row) => (
        <Fragment key={row.entity}>
          <div className="trow">
            <div>
              <b>{row.entity}</b>
              {row.sentenceOnly && <small>tone of the sentences naming it</small>}
            </div>
            <div className="pills">
              {row.entries.map((s) => <span className="pill" key={s.source}>{s.source}: <b>{s.frame}</b></span>)}
            </div>
          </div>
          <details className="ex">
            <summary>Example sentences</summary>
            {row.entries.map((s) => (
              <div className="quote" key={s.source}>
                <div>
                  <span className="qsrc">{s.source}</span>
                  <span className="qtone">{plural(s.mentions ?? 1, 'mention')}</span>
                </div>
                <blockquote>
                  {trim(s.example, 230)}
                  <span className="qmark">this sentence on its own reads {s.example_frame || s.frame}</span>
                </blockquote>
              </div>
            ))}
          </details>
        </Fragment>
      ))}
    </>
  )
}

function FigureRow({ row }: { row: Figure }) {
  const tags = figureTags(row)
  const ctx = figureInContext(row)
  const link = safeUrl(row.url)
  return (
    <div className="fig">
      <div className="fhead">
        <span className="fnum">{row.figure}</span>
        <span className="fsrc">{row.source}</span>
        {tags.map((t) => <span className="ftag" key={t}>{t}</span>)}
      </div>
      <p className="fctx">
        {ctx.cutStart && '…'}{ctx.before}{ctx.figure && <strong>{ctx.figure}</strong>}{ctx.after}{ctx.cutEnd && '…'}
        {link && <> <a href={link} target="_blank" rel="noopener noreferrer">read the original</a></>}
      </p>
    </div>
  )
}

function NumbersSection({ numbers }: { numbers: Numbers }) {
  const { groups, ungrouped, solo } = numbers
  const extra = ungrouped.length + solo.length
  return (
    <>
      <h2>The numbers</h2>
      <p className="hint">Each number with the sentence it came from. Read the sentence: two numbers can count different things.</p>
      {!groups.length && !extra && <p className="empty">No outlet published a figure we could classify for this story.</p>}
      {groups.map((g, i) => (
        <Fragment key={`${g.unit}-${i}`}>
          <p className="fgroup">{g.sources.length} outlets gave a figure in <b>{g.unit}</b> for the same thing:</p>
          {g.values.map((row, j) => <FigureRow key={j} row={row} />)}
        </Fragment>
      ))}
      {extra > 0 && (
        <details className="pdet" open={!groups.length}>
          <summary>
            <b>{groups.length ? 'More numbers' : 'Numbers in this story'}</b>
            <span>{plural(extra, 'figure')} with nothing to set beside</span>
          </summary>
          <div className="pbody">
            {ungrouped.length > 0 && (
              <>
                <h4 className="fsub">Same kind of figure, possibly not the same thing</h4>
                <p className="hint">Too far apart to call one quantity: a national total and a county total can both be true. Read the sentences.</p>
                {ungrouped.map((row, j) => <FigureRow key={j} row={row} />)}
              </>
            )}
            {solo.length > 0 && (
              <>
                <h4 className="fsub">Reported by one outlet only</h4>
                {solo.map((row, j) => <FigureRow key={j} row={row} />)}
              </>
            )}
          </div>
        </details>
      )}
    </>
  )
}

/** Who covered the story, and what differs; unread outlets named as such, never as leaving facts out. */
function Side({ story, outlets, known }: { story: Story; outlets: Outlets; known: Set<string> }) {
  const { read, unread } = outlets
  const gaps = gapsIn(story.analysis?.coverage ?? [])
  const reasons = story.analysis?.differences.reasons ?? []
  const first = firstArticles(story.articles)
  const all = [...new Set([...read, ...unread])].sort()
  return (
    <aside className="side">
      <div className="panel">
        <h4>Coverage at a glance</h4>
        <p className="sub">The outlets that covered this story</p>
        <div className="minis">
          <div className="mini">
            <span className="t">Outlets</span>
            <span className="n">{all.length}</span>
            <small>{unread.length ? `${read.length} read · ${unread.length} could not open` : 'all could be read'}</small>
          </div>
          <div className="mini">
            <span className="t">Articles</span>
            <span className="n">{story.articles.length}</span>
            <small>in this story</small>
          </div>
        </div>
        {story.analysis && (
          <>
            <h5>What differs</h5>
            <div className="badges start">
              {gaps > 0 && <span className="badge gap">{plural(gaps, 'fact')} not in every outlet</span>}
              {reasons.map((r) => <span className="badge sim" key={r}>{r}</span>)}
              {!gaps && !reasons.length && <span className="badge ok">same facts in every outlet we read</span>}
            </div>
          </>
        )}
        <h5>Outlets</h5>
        <ul className="outlets">
          {all.map((outlet) => {
            const isUnread = unread.includes(outlet)
            const link = safeUrl(first.get(outlet)?.url)
            return (
              <li key={outlet} className={isUnread ? 'no' : undefined}>
                <Avatar name={outlet} muted={isUnread} />
                <span><OutletName name={outlet} known={known} /></span>
                {isUnread ? <span className="tag">could not open</span>
                  : link ? <a className="go" href={link} target="_blank" rel="noopener noreferrer">Read <OutIcon /></a> : null}
              </li>
            )
          })}
        </ul>
        <p className="fine">Differences show what each outlet included and how it worded it. They do not say which account is correct.</p>
      </div>
    </aside>
  )
}

export function StoryPage() {
  const { story, known: knownList } = useLoaderData<typeof storyLoader>()
  const known = useMemo(() => new Set(knownList), [knownList])
  const location = useLocation()
  const navigate = useNavigate()
  const reduced = usePrefersReducedMotion()
  const tabs = useMemo(() => tabsFor(story), [story])
  const outlets = readOutlets(story)

  const wanted = location.hash.slice(1) as TabId
  const active: TabId = tabs.some((t) => t.id === wanted) ? wanted : 'overview'
  // the panel slides in from the side it was asked from
  const order = tabs.map((t) => t.id)
  const last = useRef<TabId>(active)
  const direction = order.indexOf(active) < order.indexOf(last.current) ? 'back' : 'fwd'
  useEffect(() => { last.current = active }, [active])

  const select = (id: TabId) => {
    void navigate({ hash: id === 'overview' ? '' : `#${id}` }, { replace: true, preventScrollReset: true })
  }

  // "Read the originals" opens the overview at the headlines
  const [jump, setJump] = useState(0)
  useEffect(() => {
    if (jump) document.getElementById('headlines')?.scrollIntoView({ block: 'start', behavior: reduced ? 'auto' : 'smooth' })
  }, [jump, reduced])

  const sources = story.outlets.length
  const dates = story.articles.map((a) => a.published).filter((d): d is string => !!d).sort()
  const analysis = story.analysis
  const loose = story.coherence !== null && story.coherence < 0.5

  let panel: ReactNode
  if (active === 'facts' && analysis) {
    panel = (
      <>
        <h2>What each outlet reported</h2>
        <p className="hint">Each row is a fact from one of the articles. Read across to see which outlets reported it.</p>
        <CoverageTable coverage={analysis.coverage} outlets={outlets} />
      </>
    )
  } else if (active === 'quotes' && analysis) {
    panel = <Quotes remarks={analysis.quotes} />
  } else if (active === 'tone' && analysis) {
    panel = <ToneSection story={story} />
  } else if (active === 'numbers' && analysis) {
    panel = <NumbersSection numbers={analysis.numbers} />
  } else {
    panel = (
      <>
        {loose && (
          <div className="loose">
            <b>We are not confident these are one story.</b> These articles score {story.coherence?.toFixed(2)} on our
            similarity check, below the 0.50 floor, so read the comparison with that in mind.
          </div>
        )}
        {!analysis && (
          <div className="loose calm">
            <b>Not compared yet.</b> Newseye has grouped these articles but not yet read them side by side. Each
            outlet’s headline is below.
          </div>
        )}
        {analysis && <Glance story={story} onTab={select} />}
        <Headlines articles={story.articles} known={known} />
        {story.people.length > 0 && (
          <div className="people">
            <p className="hint">People in this story: open one to see how each outlet covers them across all stories.</p>
            <div className="pchips">
              {story.people.map((p) => <Link className="pchip" key={p.id} to={`/people/${p.id}`} viewTransition>{p.name}</Link>)}
            </div>
          </div>
        )}
      </>
    )
  }

  const headline = trim(story.headline ?? 'Untitled story', 110)
  return (
    <>
      <title>{`${headline} · Newseye`}</title>
      <div className="crumb"><Link to="/" viewTransition>Stories</Link><span>/</span><span>Story {story.id}</span></div>
      <div className="phead">
        <div>
          <h1 style={{ viewTransitionName: `story-title-${story.id}` }}>{headline}</h1>
          <p className="pmeta">
            How {sources} Kenyan outlets covered this story · {plural(story.articles.length, 'article')}
            {dates.length > 0 && ` · first reported ${day(dates[0])} · latest ${day(dates[dates.length - 1])}`}
          </p>
        </div>
        <button type="button" className="btn line" onClick={() => { select('overview'); setJump((j) => j + 1) }}>
          Read the originals
        </button>
      </div>
      <div className="tabs">
        <Tabs tabs={tabs} active={active} onSelect={select} label="Sections of this story" />
        <div className="story">
          <div>
            <section key={active} id={`panel-${active}`} role="tabpanel" aria-labelledby={`tab-${active}`}
              className={`card tabpanel in-${direction}`}>
              {panel}
            </section>
            <footer className="end">Newseye compares what each outlet included. It does not rate outlets or tell you who to trust.</footer>
          </div>
          <Side story={story} outlets={outlets} known={known} />
        </div>
      </div>
    </>
  )
}
