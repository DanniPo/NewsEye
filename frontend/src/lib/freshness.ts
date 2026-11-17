import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useRevalidator } from 'react-router'

import { api, clearCache } from '../api/client'
import type { Health } from '../api/types'

/*
 * Keeping an open page current. Each pipeline run stores new results, and the API
 * serves whatever is stored. An open page asks the API every POLL_MS whether
 * anything has been stored since it last looked, and again when the reader comes
 * back to the tab. It acts only once a run has finished, so a reader never sees a
 * run half-way through:
 *
 * - a list (stories, contested, people, sources, search) reloads its data in
 *   place and says so for a moment;
 * - a story or a person, which the reader may be in the middle of, says newer
 *   results are in and leaves the reload to them. A re-grouping can end a story,
 *   and the page must not vanish while it is being read.
 */

/** How often an open page asks whether a run has stored something new. */
export const POLL_MS = 120_000
/** How long "updated" stays on screen. */
const NOTE_MS = 6_000

/** Pages a reader is in the middle of: refreshed only when they ask. */
const READING = /^\/(stories|people)\/[^/]+/

/** Everything a run can change that a page shows. */
export function signature(health: Health): string {
  return [
    health.articles, health.stories, health.analysed, health.people, health.last_article,
    health.last_clustered, health.last_analysed ?? '', health.people_built ?? '',
  ].join('|')
}

export type FreshState = 'idle' | 'updated' | 'waiting'

export function useFreshness(pollMs = POLL_MS): { state: FreshState; refresh: () => void } {
  const { pathname } = useLocation()
  const revalidator = useRevalidator()
  const revalidate = useRef(revalidator.revalidate)
  revalidate.current = revalidator.revalidate
  const reading = useRef(READING.test(pathname))
  reading.current = READING.test(pathname)
  const seen = useRef<string | null>(null)
  const [state, setState] = useState<FreshState>('idle')

  const refresh = useCallback(() => {
    clearCache()
    setState('idle')
    void revalidate.current()
  }, [])

  useEffect(() => {
    let alive = true
    let busy = false
    const check = async () => {
      if (busy || document.visibilityState === 'hidden') return
      busy = true
      try {
        const health = await api.health({ fresh: true })
        const now = signature(health)
        if (seen.current === null) {
          seen.current = now
          return
        }
        // nothing new, or a run still going: look again later
        if (now === seen.current || health.pipeline_running) return
        seen.current = now
        // whatever page comes next is fetched afresh, not from the minute-long cache
        clearCache()
        if (!alive) return
        if (reading.current) {
          setState('waiting')
        } else {
          void revalidate.current()
          setState('updated')
        }
      } catch {
        // the API could not be reached: the next check tries again, and a page
        // shows its own errors when it loads
      } finally {
        busy = false
      }
    }
    void check()
    const timer = window.setInterval(() => void check(), pollMs)
    const onVisible = () => {
      if (document.visibilityState !== 'hidden') void check()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      alive = false
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [pollMs])

  // another page is loaded fresh, so a note about the last one no longer applies
  useEffect(() => {
    setState('idle')
  }, [pathname])

  useEffect(() => {
    if (state !== 'updated') return
    const timer = window.setTimeout(() => setState('idle'), NOTE_MS)
    return () => window.clearTimeout(timer)
  }, [state])

  return { state, refresh }
}
