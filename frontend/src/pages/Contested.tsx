import { useLoaderData } from 'react-router'
import type { LoaderFunctionArgs } from 'react-router'

import { api } from '../api/client'
import { StoryCard } from '../components/StoryCard'
import { fullDate, plural } from '../lib/format'

const DAYS = 7

export async function contestedLoader({ request }: LoaderFunctionArgs) {
  return api.contested({ limit: 30, days: DAYS }, { signal: request.signal })
}

/**
 * The latest stories whose coverage reports a dispute, most contested first. What
 * counts is what the headlines and quotes report, and each card says what was
 * counted. It is not a finding that the outlets disagree, and the page says so.
 */
export function Contested() {
  const page = useLoaderData<typeof contestedLoader>()
  const span = page.until ? `the ${page.days} days to ${fullDate(page.until)}` : `the last ${page.days} days`
  return (
    <>
      <title>Contested stories · Newseye</title>
      <section className="intro">
        <h1>Contested stories</h1>
        <p>
          The latest stories whose coverage reports a dispute: headlines about accusations, denials, rows,
          probes, arrests or protests, and quotes reported as criticism or denial. Each card says what was
          counted. This is about what the stories report, not about which outlet is right: open one to
          compare how each outlet covered it.
        </p>
        <p className="meta">{plural(page.items.length, 'story', 'stories')} from {span}, most contested first.</p>
      </section>
      {page.items.length ? (
        <div className="grid">
          {page.items.map((story, i) => (
            <StoryCard key={story.id} story={story} index={i} why={story.contention.reasons.join(' · ')} />
          ))}
        </div>
      ) : (
        <div className="empty-grid">No story in this window has headlines or quotes that report a dispute.</div>
      )}
    </>
  )
}
