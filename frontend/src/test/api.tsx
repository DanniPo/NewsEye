// A fake API behind fetch: each test says what each path answers, and can read
// back every request the page made.

import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { vi } from 'vitest'

import { routes } from '../routes'
import {
  CONTESTED,
  PAGE,
  PEOPLE,
  PERSON,
  RESULTS,
  SOURCE,
  SOURCES,
  STORY,
  TOPICS,
} from './fixtures'

export type Answer = unknown | ((url: URL) => Response | unknown)

export const DEFAULTS: Record<string, Answer> = {
  '/api/stories': PAGE,
  '/api/topics': TOPICS,
  '/api/sources': SOURCES,
  '/api/sources/capital-fm': SOURCE,
  '/api/stories/1387': STORY,
  '/api/contested': CONTESTED,
  '/api/people': PEOPLE,
  '/api/people/william-ruto': PERSON,
  '/api/search': RESULTS,
}

export function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } })
}

/** Stub fetch with the default answers, overridden by `answers`; 404 for anything else. */
export function mockApi(answers: Record<string, Answer> = {}) {
  const table = { ...DEFAULTS, ...answers }
  const calls: URL[] = []
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://localhost')
    calls.push(url)
    const answer = table[url.pathname]
    if (answer === undefined) return json({ detail: 'No such thing' }, 404)
    const value = typeof answer === 'function' ? (answer as (u: URL) => unknown)(url) : answer
    return value instanceof Response ? value : json(value)
  })
  vi.stubGlobal('fetch', fetchMock)
  return { calls, fetchMock }
}

/** Render the whole app at a path, with the real routes and loaders. */
export function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  const user = userEvent.setup()
  const view = render(<RouterProvider router={router} />)
  return { router, user, ...view }
}
