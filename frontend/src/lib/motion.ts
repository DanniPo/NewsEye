// Motion that respects the reader. Everything animated here stops when the system
// asks for reduced motion, and the page reads the same with or without it.

import { useEffect, useState, useSyncExternalStore } from 'react'
import { flushSync } from 'react-dom'

const QUERY = '(prefers-reduced-motion: reduce)'

function subscribe(onChange: () => void) {
  if (typeof window === 'undefined' || !window.matchMedia) return () => {}
  const media = window.matchMedia(QUERY)
  media.addEventListener('change', onChange)
  return () => media.removeEventListener('change', onChange)
}

function reducedNow(): boolean {
  return typeof window !== 'undefined' && !!window.matchMedia && window.matchMedia(QUERY).matches
}

export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, reducedNow, () => true)
}

/** A number that counts up to its value once, quickly, unless motion is reduced. */
export function useCountUp(target: number, duration = 700): number {
  const reduced = usePrefersReducedMotion()
  const [value, setValue] = useState(reduced ? target : 0)
  useEffect(() => {
    if (reduced) {
      setValue(target)
      return
    }
    let frame = 0
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      setValue(Math.round(target * (1 - (1 - t) ** 3)))
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [target, duration, reduced])
  return value
}

/**
 * Show each of the first `steps` items for `interval` ms, once, then null: the
 * caller's static wording takes over. Kept under five seconds in all, so the
 * movement ends by itself and needs no pause control (WCAG 2.2.2). Null at once
 * when motion is reduced.
 */
export function useIntroCycle<T>(items: readonly T[], steps = 4, interval = 1100): T | null {
  const reduced = usePrefersReducedMotion()
  const [index, setIndex] = useState(0)
  const total = Math.min(steps, items.length)
  useEffect(() => {
    if (reduced || total < 1) return
    const timer = window.setInterval(() => {
      setIndex((i) => {
        if (i + 1 >= total) window.clearInterval(timer)
        return i + 1
      })
    }, interval)
    return () => window.clearInterval(timer)
  }, [total, interval, reduced])
  if (reduced || index >= total) return null
  return items[index]
}

/**
 * Run a state change as a view transition where the browser has them, so cards
 * glide to their new places instead of jumping. Elsewhere, or with reduced
 * motion, the change simply happens.
 */
export function withTransition(update: () => void): void {
  const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown }
  if (!doc.startViewTransition || reducedNow()) {
    update()
    return
  }
  // the new state must be on screen before the browser takes its "after" picture
  doc.startViewTransition(() => flushSync(update))
}
