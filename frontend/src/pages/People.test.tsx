import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { json, mockApi, renderAt } from '../test/api'

describe('the people pages', () => {
  it('rank people by the articles naming them, tone read out in words', async () => {
    mockApi()
    renderAt('/people')
    const table = await screen.findByRole('table')
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows[0]).toHaveTextContent('William Ruto')
    expect(rows[0]).toHaveTextContent('never named by The Sharp Daily and Amref Newsroom')
    expect(within(rows[0]).getByRole('img', { name: '20% negative, 45% neutral, 35% positive' })).toBeInTheDocument()
    expect(rows[1]).toHaveTextContent('too few headlines')
  })

  it("show each outlet's portrayal, with its words and headlines", async () => {
    mockApi()
    const { user } = renderAt('/people/william-ruto')
    expect(await screen.findByRole('heading', { level: 1, name: 'William Ruto' })).toBeInTheDocument()
    expect(screen.getByText('Named most often by', { exact: false }).closest('li')).toHaveTextContent('Named most often by Capital FM: 72 of its 609 articles.')
    const kbc = screen.getAllByText('KBC').find((el) => el.closest('summary'))!.closest('details')!
    expect(kbc).toHaveTextContent('actions: opens, tours')
    await user.click(screen.getByRole('link', { name: 'Capital FM' }))
    const capital = document.getElementById('o-capital-fm') as HTMLDetailsElement
    expect(capital.open).toBe(true)
    expect(capital).toHaveTextContent('Words for what they said: neutral: says · critical: accuses')
    expect(capital).toHaveTextContent('Ruto says housing levy will stay')
  })

  it('an outlet that never names them links to its source page', async () => {
    mockApi()
    renderAt('/people/william-ruto')
    const row = (await screen.findByText('Never named in its 105 articles')).closest('tr')!
    expect(within(row).getByRole('link', { name: 'The Sharp Daily' })).toHaveAttribute('href', '/sources/the-sharp-daily')
  })

  it('say how to build them when they have not been built', async () => {
    mockApi({ '/api/people': () => json({ detail: 'People pages have not been built: run python -m backend.people' }, 503) })
    renderAt('/people')
    expect(await screen.findByRole('heading', { name: 'Not available right now' })).toBeInTheDocument()
    expect(screen.getByText(/run python -m backend\.people/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
