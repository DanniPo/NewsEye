import type { RouteObject } from 'react-router'

import { Layout } from './components/Layout'
import { NotFound, RouteError, Skeleton } from './components/States'
import { Contested, contestedLoader } from './pages/Contested'
import { Dashboard, dashboardLoader } from './pages/Dashboard'
import { People, peopleLoader, Person, personLoader } from './pages/People'
import { Search, searchLoader } from './pages/Search'
import { SourcePage, sourceLoader, Sources, sourcesLoader } from './pages/Sources'
import { StoryPage, storyLoader } from './pages/StoryPage'

// Each page loads its data before it is shown, so a page change is one step: the
// old page, a thin progress bar, then the new page complete, which the browser can
// animate as one view transition. An error stays inside the frame, beside the
// navigation, rather than replacing the whole page.
export const routes: RouteObject[] = [
  {
    path: '/',
    Component: Layout,
    HydrateFallback: Skeleton,
    ErrorBoundary: RouteError,
    children: [
      {
        ErrorBoundary: RouteError,
        children: [
          { index: true, loader: dashboardLoader, Component: Dashboard },
          { path: 'contested', loader: contestedLoader, Component: Contested },
          { path: 'stories/:id', loader: storyLoader, Component: StoryPage },
          { path: 'people', loader: peopleLoader, Component: People },
          { path: 'people/:id', loader: personLoader, Component: Person },
          { path: 'sources', loader: sourcesLoader, Component: Sources },
          { path: 'sources/:slug', loader: sourceLoader, Component: SourcePage },
          { path: 'search', loader: searchLoader, Component: Search },
          { path: '*', Component: NotFound },
        ],
      },
    ],
  },
]
