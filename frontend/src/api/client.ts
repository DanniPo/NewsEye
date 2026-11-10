import type {
  ContestedPage,
  Person,
  PersonSummary,
  SearchResults,
  Source,
  SourceSummary,
  Story,
  StoryPage,
  StorySort,
  Topic,
} from './types'

// Where the API lives. The development server proxies /api to it (vite.config.ts);
// a hosted build can point elsewhere with VITE_API_BASE.
const BASE = ((import.meta.env.VITE_API_BASE as string | undefined) ?? '/api').replace(/\/$/, '')

// How long an answer is reused. The data changes every two hours at most, and
// reuse keeps going back and forth between pages instant and within the API's
// per-minute limit.
const TTL_MS = 60_000

export class ApiError extends Error {
  readonly status: number
  readonly retryAfter: number | null

  constructor(status: number, message: string, retryAfter: number | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.retryAfter = retryAfter
  }
}

/** What a reader is told when the API gives no reason of its own. */
export function messageFor(status: number): string {
  switch (status) {
    case 0:
      return 'Newseye could not be reached. Check your connection and try again.'
    case 404:
      return 'We could not find that.'
    case 422:
      return 'That request was not one Newseye can answer.'
    case 429:
      return 'Too many requests at once. Wait a moment and try again.'
    case 503:
      return "Newseye's stories are unavailable right now. Try again in a few minutes."
    default:
      return 'Something went wrong on our side. Try again in a moment.'
  }
}

type Params = Record<string, string | number | null | undefined>

export function apiUrl(path: string, params?: Params): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value))
  }
  const text = query.toString()
  return `${BASE}${path}${text ? `?${text}` : ''}`
}

async function request<T>(url: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, { headers: { Accept: 'application/json' } })
  } catch {
    throw new ApiError(0, messageFor(0))
  }
  if (!response.ok) {
    let detail = ''
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // not JSON: the status says enough
    }
    const wait = Number(response.headers.get('Retry-After'))
    throw new ApiError(
      response.status,
      detail || messageFor(response.status),
      Number.isFinite(wait) && wait > 0 ? wait : null,
    )
  }
  return (await response.json()) as T
}

/** Resolve with the shared answer, or reject as soon as this caller gives up. */
function untilAborted<T>(promise: Promise<T>, signal?: AbortSignal): Promise<T> {
  if (!signal) return promise
  if (signal.aborted) return Promise.reject(new DOMException('Aborted', 'AbortError'))
  return new Promise<T>((resolve, reject) => {
    const abort = () => reject(new DOMException('Aborted', 'AbortError'))
    signal.addEventListener('abort', abort, { once: true })
    promise.then(
      (value) => {
        signal.removeEventListener('abort', abort)
        resolve(value)
      },
      (error: unknown) => {
        signal.removeEventListener('abort', abort)
        reject(error)
      },
    )
  })
}

const cache = new Map<string, { at: number; value: Promise<unknown> }>()

export function clearCache(): void {
  cache.clear()
}

interface Options {
  signal?: AbortSignal
  /** skip the cache, e.g. for "Try again" */
  fresh?: boolean
}

/**
 * GET a JSON answer. Answers are shared for a minute: a page and the next page
 * asking for the same list make one request. A failed request is never kept.
 * The network request is not cancelled with the caller, so a page left half-way
 * still fills the cache for the next visit.
 */
export function getJson<T>(path: string, params?: Params, options: Options = {}): Promise<T> {
  const url = apiUrl(path, params)
  const now = Date.now()
  const hit = cache.get(url)
  if (!options.fresh && hit && now - hit.at < TTL_MS) {
    return untilAborted(hit.value as Promise<T>, options.signal)
  }
  const value = request<T>(url)
  cache.set(url, { at: now, value })
  value.catch(() => {
    if (cache.get(url)?.value === value) cache.delete(url)
  })
  return untilAborted(value, options.signal)
}

export interface StoryQuery {
  limit?: number
  offset?: number
  sort?: StorySort
  topic?: string | null
  source?: string | null
}

export const api = {
  stories: (query: StoryQuery, options?: Options) =>
    getJson<StoryPage>('/stories', { ...query }, options),
  contested: (query: { limit?: number; days?: number }, options?: Options) =>
    getJson<ContestedPage>('/contested', query, options),
  topics: (options?: Options) => getJson<Topic[]>('/topics', undefined, options),
  story: (id: number, options?: Options) => getJson<Story>(`/stories/${id}`, undefined, options),
  search: (q: string, limit: number, options?: Options) =>
    getJson<SearchResults>('/search', { q, limit }, options),
  people: (options?: Options) => getJson<PersonSummary[]>('/people', undefined, options),
  person: (id: string, options?: Options) =>
    getJson<Person>(`/people/${encodeURIComponent(id)}`, { records: 60 }, options),
  sources: (options?: Options) => getJson<SourceSummary[]>('/sources', undefined, options),
  source: (slug: string, options?: Options) =>
    getJson<Source>(`/sources/${encodeURIComponent(slug)}`, undefined, options),
}
