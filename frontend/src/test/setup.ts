import '@testing-library/jest-dom/vitest'

import { cleanup, configure } from '@testing-library/react'
import { afterEach, beforeEach, vi } from 'vitest'

import { clearCache } from '../api/client'

// the whole app renders in jsdom, which is slow: give findBy* time to wait
configure({ asyncUtilTimeout: 5000 })

// jsdom has no layout: give it what the app calls, and ask for reduced motion so
// counts show their final value at once and nothing waits on an animation
beforeEach(() => {
  window.matchMedia = vi.fn((query: string) => ({
    matches: query.includes('prefers-reduced-motion'),
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia
  window.scrollTo = vi.fn() as unknown as typeof window.scrollTo
  Element.prototype.scrollIntoView = vi.fn()
})

afterEach(() => {
  cleanup()
  clearCache()
  vi.unstubAllGlobals()
})
