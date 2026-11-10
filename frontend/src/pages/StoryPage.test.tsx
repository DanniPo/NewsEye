import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { json, mockApi, renderAt } from '../test/api'
import { STORY } from '../test/fixtures'

describe('a story page', () => {
  it('opens on the overview: what differs at a glance, and every headline', async () => {
    mockApi()
    renderAt('/stories/1387')
    expect(await screen.findByRole('heading', { level: 1, name: STORY.headline! })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText(/We could open 2 of the 3 outlets' articles/)).toBeInTheDocument()
    const headlines = screen.getByRole('heading', { name: 'Headlines' }).closest('div')!
    expect(within(headlines).getByText('could not open')).toBeInTheDocument()
  })

  it('never makes a link of an unsafe article address (DEF-27)', async () => {
    mockApi()
    renderAt('/stories/1387')
    const title = await screen.findByText('Kenya Warns Nigeria Over Treatment of Kenyans Seeking Visas', { selector: 'span' })
    expect(title.closest('a')).toBeNull()
    const safe = screen.getByText("Kenya protests 'unacceptable' treatment of citizens seeking Nigerian visas")
    expect(safe.closest('a')).toHaveAttribute('href', 'https://www.capitalfm.co.ke/news/a')
    expect(safe.closest('a')).toHaveAttribute('rel', 'noopener noreferrer')
    expect(document.querySelector('a[href^="javascript:"]')).toBeNull()
  })

  it('switches tabs in place, with the facts table naming only outlets it could read', async () => {
    mockApi()
    const { user, router } = renderAt('/stories/1387')
    await user.click(await screen.findByRole('tab', { name: /Facts/ }))
    expect(screen.getByRole('tab', { name: /Facts/ })).toHaveAttribute('aria-selected', 'true')
    expect(router.state.location.hash).toBe('#facts')
    const table = screen.getByRole('table')
    const heads = within(table).getAllByRole('columnheader').map((th) => th.textContent)
    expect(heads).toEqual(['What was reported', 'Capital FM', 'The Kenya Times'])
    expect(screen.getByText(/Not in the table: People Daily/)).toBeInTheDocument()
    expect(within(table).getByText('The Kenya Times did not report this')).toBeInTheDocument()
  })

  it('moves between tabs with the arrow keys', async () => {
    mockApi()
    const { user } = renderAt('/stories/1387')
    const overview = await screen.findByRole('tab', { name: 'Overview' })
    overview.focus()
    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('tab', { name: /Facts/ })).toHaveFocus()
    await user.keyboard('{End}')
    expect(screen.getByRole('tab', { name: /Numbers/ })).toHaveAttribute('aria-selected', 'true')
  })

  it('a link in the overview opens its tab', async () => {
    mockApi()
    const { user } = renderAt('/stories/1387')
    await user.click(await screen.findByRole('button', { name: 'See them side by side' }))
    expect(screen.getByRole('tab', { name: /Numbers/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('2 outlets gave a figure in', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('according to ministry')).toBeInTheDocument()
  })

  it('shows each version of a shared remark, marking what the longer one adds', async () => {
    mockApi()
    renderAt('/stories/1387#quotes')
    expect(await screen.findByText('Adds to it')).toBeInTheDocument()
    expect([...document.querySelectorAll('mark')].map((m) => m.textContent)).toEqual(['of', 'our', 'citizens'])
    expect(screen.getByText('Other quotes')).toBeInTheDocument()
  })

  it('links each outlet to its source page and the people named to theirs', async () => {
    mockApi()
    renderAt('/stories/1387')
    const side = (await screen.findByRole('heading', { name: 'Coverage at a glance' })).closest('aside')!
    expect(within(side).getByRole('link', { name: 'Capital FM' })).toHaveAttribute('href', '/sources/capital-fm')
    expect(within(side).getByText('could not open')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Musalia Mudavadi' })).toHaveAttribute('href', '/people/musalia-mudavadi')
  })

  it("a story with no page says why, in the API's words", async () => {
    mockApi({ '/api/stories/13': () => json({ detail: 'This story has no page: its articles are too loosely related to compare' }, 404) })
    renderAt('/stories/13')
    expect(await screen.findByRole('heading', { name: 'We could not find that' })).toBeInTheDocument()
    expect(screen.getByText(/too loosely related to compare/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to the stories' })).toBeInTheDocument()
  })

  it('a story not yet compared shows its headlines and no comparison tabs', async () => {
    mockApi({ '/api/stories/1410': { ...STORY, id: 1410, status: 'not analysed', analysis: null, people: [] } })
    renderAt('/stories/1410')
    expect(await screen.findByText('Not compared yet.')).toBeInTheDocument()
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(['Overview'])
  })
})
