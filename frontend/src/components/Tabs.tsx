import { useLayoutEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'

export interface TabItem<T extends string> {
  id: T
  label: string
  count?: number | null
}

interface Props<T extends string> {
  tabs: TabItem<T>[]
  active: T
  onSelect: (id: T) => void
  label: string
}

/**
 * A tab bar whose highlight slides from tab to tab. Arrow keys, Home and End move
 * between tabs as the ARIA tabs pattern describes.
 */
export function Tabs<T extends string>({ tabs, active, onSelect, label }: Props<T>) {
  const bar = useRef<HTMLDivElement>(null)
  const [pill, setPill] = useState<{ left: number; width: number } | null>(null)

  useLayoutEffect(() => {
    const place = () => {
      const button = bar.current?.querySelector<HTMLButtonElement>(`[data-tab="${active}"]`)
      if (button) setPill({ left: button.offsetLeft, width: button.offsetWidth })
    }
    place()
    if (typeof ResizeObserver === 'undefined' || !bar.current) return
    const observer = new ResizeObserver(place)
    observer.observe(bar.current)
    return () => observer.disconnect()
  }, [active, tabs.length])

  const move = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = tabs.findIndex((t) => t.id === active)
    const next = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: tabs.length - 1 }[event.key]
    if (next === undefined) return
    event.preventDefault()
    const target = tabs[(next + tabs.length) % tabs.length]
    onSelect(target.id)
    bar.current?.querySelector<HTMLButtonElement>(`[data-tab="${target.id}"]`)?.focus()
  }

  return (
    <div className="tabbar" role="tablist" aria-label={label} ref={bar} onKeyDown={move}>
      {pill && <span className="tabpill" style={{ transform: `translateX(${pill.left}px)`, width: pill.width }} aria-hidden="true" />}
      {tabs.map((tab) => {
        const on = tab.id === active
        return (
          <button key={tab.id} type="button" role="tab" id={`tab-${tab.id}`} data-tab={tab.id}
            aria-selected={on} aria-controls={`panel-${tab.id}`} tabIndex={on ? 0 : -1}
            className={on ? 'on' : undefined} onClick={() => onSelect(tab.id)}>
            {tab.label}
            {tab.count ? <small>{tab.count}</small> : null}
          </button>
        )
      })}
    </div>
  )
}
