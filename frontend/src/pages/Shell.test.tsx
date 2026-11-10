import { act, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { CountUp } from '../components/Bits'
import { json, mockApi, renderAt } from '../test/api'

describe('the frame around every page', () => {
  it('has six places in the rail, Sources among them, and no snapshot card', async () => {
    mockApi()
    renderAt('/sources')
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    expect(within(nav).getAllByRole('link').map((a) => a.textContent)).toEqual([
      'Stories', 'Contested', 'People', 'Sources', 'Search', 'How it works',
    ])
    expect(within(nav).getByRole('link', { name: 'Sources' })).toHaveClass('on')
    expect(document.querySelector('.snap, .stamp')).toBeNull()
  })

  it('lists contested stories with what was counted', async () => {
    mockApi()
    renderAt('/contested')
    expect(await screen.findByText('2 of 3 headlines report a dispute · International')).toBeInTheDocument()
    expect(screen.getByText(/1 story from the 7 days to 27 October 2026/)).toBeInTheDocument()
  })

  it('an address that is no page says so, inside the frame', async () => {
    mockApi()
    renderAt('/no/such/page')
    expect(await screen.findByRole('heading', { name: 'No such page' })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument()
  })

  it('the database being down is said plainly, with a way to try again', async () => {
    let down = true
    mockApi({ '/api/contested': () => (down ? json({ detail: 'Database unavailable' }, 503) : { days: 7, until: null, items: [] }) })
    const { user } = renderAt('/contested')
    expect(await screen.findByRole('heading', { name: 'Not available right now' })).toBeInTheDocument()
    expect(screen.getByRole('alert')).not.toHaveTextContent(/password|host|traceback/i)
    down = false
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('No story in this window has headlines or quotes that report a dispute.')).toBeInTheDocument()
  })
})

describe('motion', () => {
  it('with reduced motion, counts show their value at once', () => {
    render(<CountUp value={8072} />)
    expect(screen.getByText('8,072')).toBeInTheDocument()
  })

  it('otherwise counts run up, while screen readers get the value at once', async () => {
    window.matchMedia = vi.fn((query: string) => ({
      matches: false, media: query, onchange: null, addEventListener: vi.fn(), removeEventListener: vi.fn(),
      addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
    })) as unknown as typeof window.matchMedia
    vi.useFakeTimers({ toFake: ['requestAnimationFrame', 'cancelAnimationFrame', 'performance'] })
    try {
      render(<CountUp value={59} />)
      expect(screen.getByText('59', { selector: '.sr-only' })).toBeInTheDocument()
      expect(screen.getByText('0', { selector: '[aria-hidden="true"]' })).toBeInTheDocument()
      await act(async () => { vi.advanceTimersByTime(1000) })
      expect(screen.getByText('59', { selector: '[aria-hidden="true"]' })).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })
})
