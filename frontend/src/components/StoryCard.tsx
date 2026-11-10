import type { CSSProperties } from 'react'
import { Link } from 'react-router'

import type { StorySummary } from '../api/types'
import { plural, trim } from '../lib/format'
import { cardSummary } from '../lib/story'
import { FlameIcon } from './Icons'

interface Props {
  story: StorySummary
  /** why the card is on this list (the Contested page says what was counted) */
  why?: string
  /** its place in the list, for the staggered entrance */
  index?: number
}

/**
 * Headline, who covered it, and in a few words what differs: the differences a
 * reader can check on the story page, never a verdict on them. The headline and
 * the card carry view-transition names, so opening a story carries the headline
 * into the story page and re-ordering the list moves cards rather than redrawing them.
 */
export function StoryCard({ story, why, index = 0 }: Props) {
  const { badges, line, meta } = cardSummary(story)
  const outlets = story.outlets
  const style = { '--i': Math.min(index, 12), viewTransitionName: `story-${story.id}` } as CSSProperties
  return (
    <Link className="tile" to={`/stories/${story.id}`} viewTransition style={style}>
      <div className="top">
        <span className="kick">{story.topic ?? 'General'}</span>
        <span className="badges">
          {badges.map((b) => <span key={b.text} className={`badge ${b.tone}`}>{b.text}</span>)}
        </span>
      </div>
      <h3 style={{ viewTransitionName: `story-title-${story.id}` }}>
        {trim(story.headline ?? 'Untitled story', 110)}
      </h3>
      {why ? (
        <p className="why"><FlameIcon /><span>{why}</span></p>
      ) : (
        <p className="desc">{line}</p>
      )}
      <div className="foot">
        <span className="ochips">
          {outlets.slice(0, 3).map((o) => <span key={o} className="ochip">{o}</span>)}
          {outlets.length > 3 && <span className="ochip">+{outlets.length - 3}</span>}
        </span>
        <span><b>{plural(outlets.length, 'outlet')}</b></span>
        {meta.map((m) => <span key={m}>{m}</span>)}
      </div>
    </Link>
  )
}
