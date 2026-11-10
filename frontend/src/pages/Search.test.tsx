import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { json, mockApi, renderAt } from '../test/api'

describe('search', () => {
  it('searches from the top bar and lists the closest articles', async () => {
    const { calls } = mockApi()
    const { user, router } = renderAt('/')
    await user.type(await screen.findByRole('searchbox', { name: /Search every article/ }), '  housing   levy {Enter}')
    expect(await screen.findByText(/2 articles close in meaning to “housing levy”/)).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/search')
    expect(calls.find((u) => u.pathname === '/api/search')!.searchParams.get('q')).toBe('housing levy')
  })

  it('links a result to its story only when it has one, and never to an unsafe address', async () => {
    mockApi()
    renderAt('/search?q=housing%20levy')
    const compare = await screen.findByRole('link', { name: /Compare how outlets covered this story/ })
    expect(compare).toHaveAttribute('href', '/stories/1387')
    expect(screen.getAllByRole('link', { name: /Compare how outlets covered/ })).toHaveLength(1)
    expect(screen.getByText('Levy row in Senate').closest('a')).toBeNull()
  })

  it('says when there have been too many searches, beside the box', async () => {
    mockApi({ '/api/search': () => json({ detail: 'Too many requests: try again shortly' }, 429, { 'Retry-After': '20' }) })
    renderAt('/search?q=floods')
    expect(await screen.findByText(/Too many searches at once.*Try again in 20 seconds/)).toBeInTheDocument()
    expect(screen.getByRole('searchbox')).toHaveValue('floods')
  })

  it('asks for at least two characters before searching', async () => {
    const { calls } = mockApi()
    renderAt('/search?q=a')
    expect(await screen.findByText('Type at least two characters.')).toBeInTheDocument()
    expect(calls.some((u) => u.pathname === '/api/search')).toBe(false)
  })
})
