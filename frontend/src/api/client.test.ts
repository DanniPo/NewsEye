import { describe, expect, it, vi } from 'vitest'

import { json, mockApi } from '../test/api'
import { PAGE } from '../test/fixtures'
import { api, ApiError, apiUrl } from './client'

describe('the API client', () => {
  it('builds addresses, leaving out empty filters', () => {
    expect(apiUrl('/stories', { limit: 12, sort: 'latest', topic: null, source: '' })).toBe('/api/stories?limit=12&sort=latest')
  })

  it('reuses an answer within a minute instead of asking again', async () => {
    const { fetchMock } = mockApi()
    await api.stories({ limit: 12 })
    await api.stories({ limit: 12 })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    await api.stories({ limit: 12 }, { fresh: true })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it("passes on the API's reason for a 404", async () => {
    mockApi({ '/api/stories/13': () => json({ detail: 'This story has no page: its articles are too loosely related to compare' }, 404) })
    await expect(api.story(13)).rejects.toMatchObject({ status: 404, message: expect.stringMatching(/too loosely related/) })
  })

  it('reads how long to wait from a 429, and never keeps a failure', async () => {
    let calls = 0
    mockApi({ '/api/topics': () => (++calls === 1 ? json({ detail: 'Too many requests: try again shortly' }, 429, { 'Retry-After': '17' }) : []) })
    const error = await api.topics().catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).retryAfter).toBe(17)
    await expect(api.topics()).resolves.toEqual([])
  })

  it('turns a network failure into a plain message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))
    await expect(api.sources()).rejects.toMatchObject({ status: 0, message: expect.stringMatching(/could not be reached/) })
  })

  it('lets a caller give up without spoiling the answer for the next one', async () => {
    mockApi()
    const controller = new AbortController()
    const first = api.stories({ limit: 5 }, { signal: controller.signal })
    controller.abort()
    await expect(first).rejects.toMatchObject({ name: 'AbortError' })
    await expect(api.stories({ limit: 5 })).resolves.toEqual(PAGE)
  })
})
