import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { mockApi, renderAt } from '../test/api'

describe('the sources pages', () => {
  it('list every outlet with counts, not ratings', async () => {
    mockApi()
    renderAt('/sources')
    expect(await screen.findByRole('heading', { name: 'Where the news comes from' })).toBeInTheDocument()
    const cards = document.querySelectorAll('.srccard')
    expect([...cards].map((c) => c.querySelector('h3')!.textContent)).toEqual([
      'K24 Digital', 'Capital FM', 'KBC', 'The Sharp Daily', 'Amref Newsroom',
    ])
    expect(document.body).not.toHaveTextContent(/rating:|score|trust/i)
    expect(screen.getByText('Counts of what each feed published, not a rating of any outlet.')).toBeInTheDocument()
  })

  it('say plainly how often each outlet could be opened', async () => {
    mockApi()
    renderAt('/sources')
    const card = (name: string) => screen.getByRole('heading', { name }).closest('a')!
    await screen.findByRole('heading', { name: 'K24 Digital' })
    expect(card('K24 Digital')).toHaveTextContent('Its article could be opened in 0 of 6 stories compared (paywall or blocked)')
    expect(card('Capital FM')).toHaveTextContent('Its articles could be opened in all 11 stories compared')
    expect(card('The Sharp Daily')).toHaveTextContent('Its article could be opened in the one story compared')
    expect(card('Amref Newsroom')).toHaveTextContent('Not yet in a story Newseye has compared')
    expect(card('KBC')).toHaveTextContent('state broadcaster')
  })

  it('reorder in place', async () => {
    mockApi()
    const { user } = renderAt('/sources')
    await screen.findByRole('heading', { name: 'K24 Digital' })
    await user.click(screen.getByRole('button', { name: 'A to Z' }))
    const names = [...document.querySelectorAll('.srccard h3')].map((h) => h.textContent)
    expect(names).toEqual(['Amref Newsroom', 'Capital FM', 'K24 Digital', 'KBC', 'The Sharp Daily'])
    await user.click(screen.getByRole('button', { name: 'Most shared stories' }))
    expect(document.querySelector('.srccard h3')!.textContent).toBe('Capital FM')
  })

  it("show one outlet's stories, topics and newest headlines", async () => {
    mockApi()
    renderAt('/sources/capital-fm')
    expect(await screen.findByRole('heading', { level: 1, name: 'Capital FM' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Visit capitalfm\.co\.ke/ })).toHaveAttribute('href', 'https://www.capitalfm.co.ke')
    const topics = screen.getByRole('heading', { name: 'What it covers' }).closest<HTMLElement>('.panel')!
    expect(within(topics).getByText('No clear topic')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'compare' })).toHaveAttribute('href', '/stories/1387')
    expect(screen.getByRole('link', { name: /See all 15 stories it covered/ })).toHaveAttribute('href', '/?source=capital-fm')
  })

  it('a source Newseye does not read is not found', async () => {
    mockApi()
    renderAt('/sources/the-daily-planet')
    expect(await screen.findByRole('heading', { name: 'We could not find that' })).toBeInTheDocument()
  })
})
