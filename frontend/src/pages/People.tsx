import { useRef } from 'react'
import type { CSSProperties } from 'react'
import { Link, useLoaderData } from 'react-router'
import type { LoaderFunctionArgs } from 'react-router'

import { api, ApiError } from '../api/client'
import type { OutletPortrayal } from '../api/types'
import { CountUp, ToneBar, ToneKey } from '../components/Bits'
import { count, day, listing, period, plural, slugOf } from '../lib/format'
import {
  CARD_MIN,
  glanceFacts,
  overallTitle,
  personHeadlines,
  ROLE_ORDER,
  ROLE_WORDS,
  roleSentence,
  STATE_MEDIA,
  topRole,
  toneTargeted,
  usualTitle,
} from '../lib/people'
import { ArticleLink } from './StoryPage'

/** how many outlets Newseye reads, when the sources list cannot be had */
const FEEDS = 12

export async function peopleLoader({ request }: LoaderFunctionArgs) {
  const [people, sources] = await Promise.all([
    api.people({ signal: request.signal }),
    api.sources({ signal: request.signal }).catch(() => []),
  ])
  const firsts = sources.map((s) => s.first).filter((d): d is string => !!d).sort()
  const lasts = sources.map((s) => s.latest).filter((d): d is string => !!d).sort()
  return { people, feeds: sources.length || FEEDS, first: firsts[0] ?? null, last: lasts.at(-1) ?? null }
}

export function People() {
  const { people, feeds, first, last } = useLoaderData<typeof peopleLoader>()
  const top = people[0]
  return (
    <>
      <title>People · Newseye</title>
      <section className="intro">
        <h1>People in the news</h1>
        <p>How each outlet presents the people it names most: how often, in what role, with which words. Pick a person to see the outlets side by side.</p>
      </section>
      <div className="stats">
        <div className="stat"><span className="t">People with a page</span><span className="n"><CountUp value={people.length} /></span><small>named in 6+ articles by 2+ outlets</small></div>
        {top && <div className="stat hi"><span className="t">Named most</span><span className="s">{top.name}</span><small>{count(top.articles)} articles</small></div>}
        <div className="stat"><span className="t">Outlets</span><span className="n"><CountUp value={feeds} /></span><small>headlines and opening lines read</small></div>
        <div className="stat"><span className="t">Period</span><span className="s">{period(first, last)}</span><small>every stored headline</small></div>
      </div>
      <section className="card">
        <h2>Most named people</h2>
        <p className="hint">Ranked by the articles naming them. Headline tone is an automatic reading and can be wrong: open a person to see the headlines behind it.</p>
        <div className="scroll">
          <table className="ptable">
            <thead>
              <tr><th>#</th><th>Person</th><th>Articles</th><th>Outlets</th><th>Headline tone</th><th><span className="sr-only">Open</span></th></tr>
            </thead>
            <tbody>
              {people.map((p, i) => {
                const never = p.never_named_by.length
                  ? `never named by ${listing(p.never_named_by.slice(0, 2))}${p.never_named_by.length > 2 ? ` and ${p.never_named_by.length - 2} more` : ''}`
                  : 'named by every outlet'
                return (
                  <tr key={p.id} className="frow" style={{ '--i': Math.min(i, 20) } as CSSProperties}>
                    <td className="rk">{String(i + 1).padStart(2, '0')}</td>
                    <td><Link className="nm" to={`/people/${p.id}`} viewTransition>{p.name}</Link>{p.title && <small>{p.title}</small>}</td>
                    <td className="num">{count(p.articles)}</td>
                    <td className="num">{p.outlets} of {feeds}<small>{never}</small></td>
                    <td><ToneBar tone={p.tone} /></td>
                    <td><Link className="open" to={`/people/${p.id}`} viewTransition aria-label={`View ${p.name}`}>View →</Link></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <ToneKey />
      </section>
    </>
  )
}

export async function personLoader({ params, request }: LoaderFunctionArgs) {
  const id = params.id ?? ''
  if (!/^[a-z0-9-]{1,80}$/.test(id)) throw new ApiError(404, 'No such person')
  const [person, sources] = await Promise.all([
    api.person(id, { signal: request.signal }),
    api.sources({ signal: request.signal }).catch(() => []),
  ])
  return { person, feeds: sources.length || FEEDS, known: sources.map((s) => s.name) }
}

function OutletCard({ outlet, s, name, cardRef }: {
  outlet: string
  s: OutletPortrayal
  name: string
  cardRef: (el: HTMLDetailsElement | null) => void
}) {
  const role = topRole(s)
  const { speaking, acting } = s.voice ?? { speaking: [], acting: [] }
  return (
    <details className="pdet" id={`o-${slugOf(outlet)}`} ref={cardRef}>
      <summary><b>{outlet}</b><span>{plural(s.articles, 'article')} · mostly {ROLE_WORDS[role]}</span></summary>
      <div className="pbody">
        <p className="psum">In {outlet}’s headlines, {roleSentence(name, s)}</p>
        {speaking.length > 0 && (
          <p className="psum">Words for what they said:{' '}
            {speaking.map((g, i) => (
              <span key={g.tone}>{i > 0 && ' · '}<span className="vt">{g.tone}:</span> {g.verbs.join(', ')}</span>
            ))}
          </p>
        )}
        {!speaking.length && acting.length > 0 && (
          <p className="psum"><span className="vt">actions:</span> {acting.join(', ')}</p>
        )}
        <ul className="heads ph">
          {personHeadlines(s.records).map((r) => (
            <li key={r.url}>
              <div>
                <span className="role">{ROLE_WORDS[r.role]}</span>
                <small>{day(r.date)}{r.field === 'snippet' ? ' · opening line' : ''}</small>
              </div>
              <ArticleLink url={r.url}>{r.headline}</ArticleLink>
            </li>
          ))}
        </ul>
        <p className="go">Open a headline to read the full article on {outlet}’s site.</p>
      </div>
    </details>
  )
}

export function Person() {
  const { person, feeds, known } = useLoaderData<typeof personLoader>()
  const cards = useRef(new Map<string, HTMLDetailsElement>())
  const named = Object.entries(person.outlets).sort((a, b) => b[1].articles - a[1].articles)
  const absent = Object.entries(person.totals)
    .filter(([o]) => !(o in person.outlets))
    .sort((a, b) => b[1] - a[1])
  const facts = glanceFacts(named, absent)
  const title = overallTitle(person)
  const targeted = toneTargeted(person)
  const span = period(person.period_first, person.period_last)
  const open = (outlet: string) => {
    const card = cards.current.get(outlet)
    if (card) {
      card.open = true
      card.scrollIntoView({ block: 'start' })
    }
  }
  return (
    <>
      <title>{`${person.name} · Newseye`}</title>
      <div className="crumb"><Link to="/people" viewTransition>People</Link><span>/</span><span>{person.name}</span></div>
      <div className="phead">
        <div>
          <h1>{person.name}</h1>
          <p className="pmeta">
            {title && <span className="kpill">{title}</span>}
            Named in {count(person.articles)} articles by {named.length} of {feeds} outlets{span && ` · ${span}`}
          </p>
        </div>
      </div>
      <div className="stats three">
        <div className="stat"><span className="t">Articles naming them</span><span className="n"><CountUp value={person.articles} /></span><small>headlines and opening lines</small></div>
        <div className="stat hi"><span className="t">Outlets</span><span className="n">{named.length} of {feeds}</span><small>{absent.length ? `never named by ${plural(absent.length, 'outlet')}` : 'named by every outlet'}</small></div>
        <div className="stat"><span className="t">Period</span><span className="s">{span}</span><small>every stored headline naming them</small></div>
      </div>
      {facts.length > 0 && (
        <section className="card">
          <h2>At a glance</h2>
          <ul className="facts">
            {facts.map((fact, i) => (
              <li key={i}>{fact.parts.map((p, j) => (p.strong ? <b key={j}>{p.text}</b> : <span key={j}>{p.text}</span>))}</li>
            ))}
          </ul>
        </section>
      )}
      <section className="card">
        <h2>Outlet by outlet</h2>
        <p className="hint">
          Counts reflect which stories each outlet covered, as well as how it wrote them.{' '}
          {targeted
            ? <><b>Headline tone</b> is an automatic reading of the writer’s attitude toward this person in each headline or opening line, not of the event: “Ruto condemns the killings” is about how Ruto is shown, not about the killings.</>
            : <><b>Headline tone</b> is an automatic reading of each headline or opening line as a whole: “Ruto condemns the killings” reads negative without being negative about Ruto.</>}
          {' '}It is a hint, not a verdict, and it can be wrong. These pages point to the reporting; they do not replace it.
        </p>
        <div className="scroll">
          <table className="glance">
            <thead><tr><th>Outlet</th><th>Called</th><th>Headline tone</th></tr></thead>
            <tbody>
              {named.map(([outlet, s]) => (
                <tr key={outlet}>
                  <td className="o">
                    {s.articles >= CARD_MIN
                      ? <a href={`#o-${slugOf(outlet)}`} onClick={(e) => { e.preventDefault(); open(outlet) }}>{outlet}</a>
                      : outlet}
                    {STATE_MEDIA[outlet] && <small>{STATE_MEDIA[outlet]}</small>}
                    <small>{plural(s.articles, 'article')}</small>
                  </td>
                  {s.articles < CARD_MIN
                    ? <td colSpan={2} className="few">Too few articles to compare</td>
                    : <><td>{usualTitle(s) || '—'}</td><td><ToneBar tone={s.tone} /></td></>}
                </tr>
              ))}
              {absent.map(([outlet, n]) => (
                <tr key={outlet} className="none">
                  <td className="o">
                    {known.includes(outlet) ? <Link to={`/sources/${slugOf(outlet)}`} viewTransition>{outlet}</Link> : outlet}
                    {STATE_MEDIA[outlet] && <small>{STATE_MEDIA[outlet]}</small>}
                  </td>
                  <td colSpan={2}>Never named in its {count(n)} articles</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ToneKey />
      </section>
      <section className="card">
        <h2>Read the coverage yourself</h2>
        <p className="hint">Open an outlet to see how its headlines present them: the part they most often play, the words used for what they said, and the headlines themselves.</p>
        {named.filter(([, s]) => s.articles >= CARD_MIN).map(([outlet, s]) => (
          <OutletCard key={outlet} outlet={outlet} s={s} name={person.name}
            cardRef={(el) => { if (el) cards.current.set(outlet, el); else cards.current.delete(outlet) }} />
        ))}
      </section>
      <details className="pdet method">
        <summary><b>How this works</b></summary>
        <div className="pbody">
          <ul className="plain">
            {ROLE_ORDER.map(({ role, words, meaning }) => <li key={role}><b>{words[0].toUpperCase() + words.slice(1)}</b>: {meaning}</li>)}
          </ul>
          {person.aliases.length > 0 && <p>Also matched as: {person.aliases.join(', ')}.</p>}
          <p>Read from headlines and opening lines, which every outlet publishes in full even when the article itself is paywalled.</p>
          <p>KBC is the state broadcaster and Kenya News the government’s own news agency: covering government activity is their remit.</p>
          <p>On a check of 40 mentions from articles collected later, the role was right 37 times. A different person with the same name can be counted under the better-known one.</p>
          <p>
            {targeted
              ? 'Headline tone comes from NewsMTSC (Hamborg and Donnay, 2021), a model trained on news to judge the writer’s attitude toward one named person. Where it cannot score a mention, the sentence’s overall tone is used. It misreads Swahili and needs local context it does not have.'
              : 'Headline tone comes from a sentiment model trained on social media posts, scoring each sentence from negative to positive. It reads the sentence, not the outlet’s view of the person, and it misreads sarcasm and Swahili.'}
          </p>
          <p>Nothing here rates an outlet or a person. The conclusion is yours.</p>
        </div>
      </details>
    </>
  )
}
