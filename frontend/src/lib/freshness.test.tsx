import { act, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { Health } from '../api/types'
import { mockApi, renderAt } from '../test/api'
import { CARD, HEALTH, PAGE } from '../test/fixtures'
import { signature } from './freshness'

const asked = (calls: URL[], path: string) => calls.filter((u) => u.pathname === path).length

/** what the page does when the reader comes back to the tab: ask again */
async function lookAgain(calls: URL[]) {
  const before = asked(calls, '/api/health')
  document.dispatchEvent(new Event('visibilitychange'))
  await waitFor(() => expect(asked(calls, '/api/health')).toBe(before + 1))
  // let the answer be read before the next look
  await act(() => new Promise((resolve) => setTimeout(resolve, 20)))
}

describe('keeping an open page current after a pipeline run', () => {
  it('counts everything a run can change that a page shows', () => {
    const base = signature(HEALTH)
    const changes: Partial<Health>[] = [
      { articles: 2986 }, { stories: 15 }, { analysed: 10 }, { people: 55 },
      { last_article: '2026-10-27T18:00:00+03:00' }, { last_clustered: '2026-10-27T18:00:00+03:00' },
      { last_analysed: '2026-10-27T18:00:00+03:00' }, { people_built: '2026-10-28T09:00:00+03:00' },
    ]
    for (const change of changes) expect(signature({ ...HEALTH, ...change })).not.toBe(base)
    expect(signature({ ...HEALTH, pipeline_running: true })).toBe(base)
  })

  it('a list refreshes itself once a run has finished, never half-way through', async () => {
    let health: Health = HEALTH
    let headline = CARD.headline!
    const { calls } = mockApi({
      '/api/health': () => health,
      '/api/stories': () => ({ ...PAGE, items: [{ ...CARD, headline }] }),
    })
    renderAt('/')
    await screen.findByRole('heading', { name: CARD.headline! })
    await waitFor(() => expect(asked(calls, '/api/health')).toBe(1))
    await act(() => new Promise((resolve) => setTimeout(resolve, 20)))

    // a run is going: something new is stored, but the page waits
    health = { ...HEALTH, analysed: 10, pipeline_running: true }
    headline = 'Floods displace families in Tana River'
    await lookAgain(calls)
    expect(screen.queryByRole('heading', { name: headline })).toBeNull()

    // the run has finished: the page reloads its data in place and says so
    health = { ...health, pipeline_running: false }
    await lookAgain(calls)
    expect(await screen.findByRole('heading', { name: headline })).toBeInTheDocument()
    expect(screen.getByText('Updated with the latest stories')).toBeInTheDocument()
  })

  it('nothing new, nothing reloaded', async () => {
    const { calls } = mockApi()
    renderAt('/')
    await screen.findByRole('heading', { name: CARD.headline! })
    await waitFor(() => expect(asked(calls, '/api/health')).toBe(1))
    await act(() => new Promise((resolve) => setTimeout(resolve, 20)))
    const stories = asked(calls, '/api/stories')
    await lookAgain(calls)
    expect(asked(calls, '/api/stories')).toBe(stories)
    expect(screen.queryByText('Updated with the latest stories')).toBeNull()
  })

  it('a story being read is not pulled away: newer results are offered, then loaded on request', async () => {
    let health: Health = HEALTH
    const { calls } = mockApi({ '/api/health': () => health })
    const { user } = renderAt('/stories/1387')
    await screen.findByRole('heading', { level: 1 })
    await waitFor(() => expect(asked(calls, '/api/health')).toBe(1))
    await act(() => new Promise((resolve) => setTimeout(resolve, 20)))
    const loads = asked(calls, '/api/stories/1387')

    health = { ...HEALTH, last_analysed: '2026-10-27T18:00:00+03:00' }
    await lookAgain(calls)
    expect(await screen.findByText(/Newer results are in/)).toBeInTheDocument()
    expect(asked(calls, '/api/stories/1387')).toBe(loads)

    await user.click(screen.getByRole('button', { name: 'Refresh this page' }))
    await waitFor(() => expect(asked(calls, '/api/stories/1387')).toBe(loads + 1))
    expect(screen.queryByText(/Newer results are in/)).toBeNull()
  })

  it('an API that cannot be reached leaves the page as it is', async () => {
    let up = true
    const { calls } = mockApi({ '/api/health': () => (up ? HEALTH : new Response('down', { status: 503 })) })
    renderAt('/')
    await screen.findByRole('heading', { name: CARD.headline! })
    await waitFor(() => expect(asked(calls, '/api/health')).toBe(1))
    up = false
    await lookAgain(calls)
    expect(screen.getByRole('heading', { name: CARD.headline! })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
