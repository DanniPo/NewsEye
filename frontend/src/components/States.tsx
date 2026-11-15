import { isRouteErrorResponse, Link, useRevalidator, useRouteError } from 'react-router'

import { ApiError, clearCache } from '../api/client'

/** Shown while the first page's data loads. */
export function Skeleton() {
  return (
    <div className="app">
      <aside className="rail" aria-hidden="true">
        <div className="brand"><span className="glyph" /><span><b>Newseye</b></span></div>
      </aside>
      <div className="main">
        <div className="topbar" />
        <main className="content" aria-busy="true" aria-label="Loading">
          <div className="sk sk-title" />
          <div className="sk sk-line" />
          <div className="sk sk-line short" />
          <div className="sk-cards">
            <div className="sk sk-card" /><div className="sk sk-card" /><div className="sk sk-card" />
          </div>
        </main>
      </div>
    </div>
  )
}

function describe(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 404) return { title: 'We could not find that', text: error.message }
    if (error.status === 429) {
      const wait = error.retryAfter ? ` Try again in ${error.retryAfter} seconds.` : ''
      return { title: 'Too many requests', text: `Newseye limits how often one reader can ask, to stay fast for everyone.${wait}`, retry: true }
    }
    if (error.status === 503) return { title: 'Not available right now', text: error.message, retry: true }
    if (error.status === 0) return { title: 'Newseye could not be reached', text: error.message, retry: true }
    return { title: 'Something went wrong', text: error.message, retry: true }
  }
  if (isRouteErrorResponse(error) && error.status === 404) {
    return { title: 'No such page', text: 'That address is not a page on Newseye.' }
  }
  return { title: 'Something went wrong', text: 'The page could not be shown. Try again in a moment.', retry: true }
}

/** Every route's error page: what happened in plain words, and a way on. */
export function RouteError() {
  const error = useRouteError()
  const revalidator = useRevalidator()
  const { title, text, retry } = describe(error)
  return (
    <section className="errorbox" role="alert">
      <h1>{title}</h1>
      <p>{text}</p>
      <div className="erractions">
        {retry && (
          <button type="button" className="btn dark" onClick={() => { clearCache(); void revalidator.revalidate() }}>
            Try again
          </button>
        )}
        <Link className="btn line" to="/" viewTransition>Back to the stories</Link>
      </div>
    </section>
  )
}

export function NotFound() {
  return (
    <section className="errorbox">
      <h1>No such page</h1>
      <p>That address is not a page on Newseye.</p>
      <div className="erractions">
        <Link className="btn line" to="/" viewTransition>Back to the stories</Link>
      </div>
    </section>
  )
}
