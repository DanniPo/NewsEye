import type { CSSProperties } from 'react'
import { Form, Link, useLoaderData, useNavigation } from 'react-router'
import type { LoaderFunctionArgs } from 'react-router'

import { api, ApiError } from '../api/client'
import { Avatar } from '../components/Bits'
import { ArrowIcon, SearchIcon } from '../components/Icons'
import { day, plural, trim } from '../lib/format'
import { ArticleLink } from './StoryPage'

const RESULTS = 20

export async function searchLoader({ request }: LoaderFunctionArgs) {
  const query = (new URL(request.url).searchParams.get('q') ?? '').split(/\s+/).filter(Boolean).join(' ')
  if (query.length < 2) return { query, results: null, problem: null }
  try {
    const found = await api.search(query, RESULTS, { signal: request.signal })
    return { query: found.query, results: found.results, problem: null }
  } catch (err) {
    // a search that cannot run is told on the page, beside the box, not as an error page
    if (err instanceof ApiError) return { query, results: null, problem: err }
    throw err
  }
}

function problemText(problem: ApiError): string {
  if (problem.status === 429) {
    return `Too many searches at once: searching by meaning runs a language model, so it is limited per reader.${problem.retryAfter ? ` Try again in ${problem.retryAfter} seconds.` : ''}`
  }
  return problem.message
}

export function Search() {
  const { query, results, problem } = useLoaderData<typeof searchLoader>()
  const navigation = useNavigation()
  const searching = navigation.state === 'loading' && navigation.location?.pathname === '/search'
  return (
    <>
      <title>{query ? `${query} · Search · Newseye` : 'Search · Newseye'}</title>
      <section className="intro">
        <h1>Search every article</h1>
        <p>Finds articles by meaning, not only by their words: “cost of living” also finds “prices of unga rise”.</p>
      </section>
      <section className="card">
        <Form className="bigsearch" action="/search" role="search">
          <SearchIcon />
          <input key={query} type="search" name="q" defaultValue={query} placeholder="Try: housing levy, floods, Gachagua"
            aria-label="Search every article by meaning" minLength={2} maxLength={200} autoComplete="off" autoFocus={!query} />
          <button type="submit">Search</button>
        </Form>
        <p className="hint" aria-live="polite">
          {searching ? 'Searching… the first search after the server starts can take a few seconds.'
            : problem ? problemText(problem)
              : results ? `${plural(results.length, 'article')} close in meaning to “${query}”, closest first.`
                : 'Type at least two characters.'}
        </p>
        {results && results.length === 0 && (
          <p className="empty">Nothing close enough. Try fewer or more general words.</p>
        )}
        {results?.map((hit, i) => (
          <article className="hit" key={hit.id} style={{ '--i': Math.min(i, 12) } as CSSProperties}>
            <div className="srcline">
              <Avatar name={hit.outlet} />
              <b>{hit.outlet}</b>
              {hit.published && <span>· {day(hit.published)}</span>}
            </div>
            <h3><ArticleLink url={hit.url}>{hit.title}</ArticleLink></h3>
            {hit.snippet && <p className="snip">{trim(hit.snippet, 220)}</p>}
            {hit.story_id !== null && (
              <Link className="hitlink" to={`/stories/${hit.story_id}`} viewTransition>
                Compare how outlets covered this story <ArrowIcon />
              </Link>
            )}
          </article>
        ))}
        <footer className="end">
          Searches are matched by meaning on Newseye’s server, against the headline and opening lines
          of every article it has collected.
        </footer>
      </section>
    </>
  )
}
