// Small pieces used across pages.

import type { Tone } from '../api/types'
import { initials, percent } from '../lib/format'
import { useCountUp, usePrefersReducedMotion } from '../lib/motion'
import { toneShares } from '../lib/people'

/** An outlet's initials in a rounded square. */
export function Avatar({ name, muted = false }: { name: string; muted?: boolean }) {
  return <span className={`av${muted ? ' no' : ''}`} aria-hidden="true">{initials(name)}</span>
}

/**
 * A count that runs up to its value once. Screen readers and tests get the final
 * value at once; the animated digits are hidden from them.
 */
export function CountUp({ value, format = (n) => n.toLocaleString('en-GB') }: {
  value: number
  format?: (n: number) => string
}) {
  const reduced = usePrefersReducedMotion()
  const shown = useCountUp(value)
  if (reduced) return <>{format(value)}</>
  return (
    <>
      <span aria-hidden="true">{format(shown)}</span>
      <span className="sr-only">{format(value)}</span>
    </>
  )
}

/**
 * A tone mix as one bar: negative, neutral, positive, with the count in words
 * beside it, so the colours are never the only key.
 */
export function ToneBar({ tone }: { tone: Tone | null | undefined }) {
  if (!tone) return <span className="few">too few headlines</span>
  const { negative, neutral, positive } = toneShares(tone)
  const words = `${percent(negative)} negative, ${percent(neutral)} neutral, ${percent(positive)} positive`
  return (
    <>
      <div className="tbar" role="img" aria-label={words} title={words}>
        <i className="ng" style={{ width: `${negative * 100}%` }} />
        <i className="nu" style={{ width: `${neutral * 100}%` }} />
        <i className="ps" style={{ width: `${positive * 100}%` }} />
      </div>
      <small>{tone.label ? `${tone.label} · ` : ''}{tone.n} headlines &amp; openings</small>
    </>
  )
}

export function ToneKey() {
  return (
    <p className="tkey">
      <span className="ng">negative</span><span>neutral</span><span className="ps">positive</span>
    </p>
  )
}

/** A share of a whole as a slim bar that grows in. */
export function ShareBar({ share, label }: { share: number; label: string }) {
  return (
    <span className="sharebar" role="img" aria-label={label} title={label}>
      <i style={{ width: `${Math.max(2, share * 100)}%` }} />
    </span>
  )
}
