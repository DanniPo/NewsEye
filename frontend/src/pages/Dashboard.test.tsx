import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { mockApi, renderAt } from '../test/api'
import { CARD, PAGE } from '../test/fixtures'

describe('the dashboard', () => {
  it('opens on the new headline, with no snapshot left anywhere', async () => {
    mockApi()
    renderAt('/')
    const heading = await screen.findByRole('heading', { level: 1 })
    expect(heading).toHaveTextContent('One story, five newsrooms. See how each one tells it.')
    expect(document.body).not.toHaveTextContent(/snapshot/i)
    expect(document.body).not.toHaveTextContent(/data as of/i)
    expect(document.title).toBe('Newseye: Kenyan news compared')
  })

  it('shows the sources, each linking to its own page', async () => {
    mockApi()
    renderAt('/')
    const card = await screen.findByRole('region', { name: 'Our sources' })
    const links = within(card).getAllByRole('link')
    expect(links.map((a) => a.getAttribute('href'))).toEqual([
      '/sources', '/sources/k24-digital', '/sources/capital-fm', '/sources/kbc', '/sources/the-sharp-daily', '/sources/amref-newsroom',
    ])
    expect(card).toHaveTextContent('2,985 articles read from their public feeds · newest 27 Oct')
  })

  it('counts outlets and stories to compare', async () => {
    mockApi()
    renderAt('/')
    expect(await screen.findByText('Outlets read')).toBeInTheDocument()
    const stories = screen.getByText('Stories to compare', { selector: '.t' }).closest('.stat')!
    expect(stories).toHaveTextContent('14')
  })

  it('orders and filters the list through the address, and asks the API for it', async () => {
    const { calls } = mockApi()
    const { user, router } = renderAt('/')
    await screen.findByRole('heading', { name: CARD.headline! })
    await user.click(screen.getByRole('button', { name: 'Latest' }))
    await screen.findByRole('button', { name: 'Latest', pressed: true })
    expect(router.state.location.search).toBe('?sort=latest')
    await user.click(screen.getByRole('button', { name: /^Politics/ }))
    await screen.findByRole('button', { name: /^Politics/, pressed: true })
    expect(router.state.location.search).toBe('?sort=latest&topic=Politics')
    const asked = calls.filter((u) => u.pathname === '/api/stories' && u.searchParams.get('limit') === '12').at(-1)!
    expect(Object.fromEntries(asked.searchParams)).toEqual({ limit: '12', sort: 'latest', topic: 'Politics' })
  })

  it('puts General last among the categories', async () => {
    mockApi()
    renderAt('/')
    const group = await screen.findByRole('group', { name: 'News categories' })
    const names = within(group).getAllByRole('button').map((b) => b.querySelector('b')!.textContent)
    expect(names).toEqual(['All stories', 'Politics', 'International', 'General'])
  })

  it('narrows to one outlet from the address, and can drop the filter', async () => {
    const { calls } = mockApi()
    const { user, router } = renderAt('/?source=capital-fm')
    expect(await screen.findByText('Capital FM', { selector: '.filterchip b' })).toBeInTheDocument()
    expect(calls.some((u) => u.searchParams.get('source') === 'capital-fm')).toBe(true)
    await user.click(screen.getByRole('button', { name: /Show stories from every outlet/ }))
    await screen.findByRole('heading', { name: 'Stories to compare' })
    expect(router.state.location.search).toBe('')
  })

  it('loads more stories on request, after the ones shown', async () => {
    const more = { ...PAGE, offset: 3, items: [{ ...CARD, id: 2001, headline: 'Floods displace families in Tana River' }] }
    mockApi({ '/api/stories': (url: URL) => (url.searchParams.get('offset') === '3' ? more : PAGE) })
    const { user } = renderAt('/')
    await user.click(await screen.findByRole('button', { name: 'Show more stories (11 left)' }))
    expect(await screen.findByRole('heading', { name: 'Floods displace families in Tana River' })).toBeInTheDocument()
  })

  it('cards say why a story has nothing to compare, instead of counting gaps', async () => {
    mockApi()
    renderAt('/')
    expect(await screen.findByText('only one outlet could be read')).toBeInTheDocument()
    expect(screen.getByText('not compared yet')).toBeInTheDocument()
  })

  it('opens "How it works" when the rail asks for it', async () => {
    mockApi()
    renderAt('/#about')
    const box = (await screen.findByText('How it works', { selector: 'summary' })).closest('details')!
    await waitFor(() => expect(box).toHaveAttribute('open'))
    expect(box).toHaveTextContent('Some sites could not always be opened (paywall or blocked): K24 Digital and KBC.')
  })
})
