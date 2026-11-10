import { Form, NavLink, Outlet, ScrollRestoration, useLocation, useNavigation } from 'react-router'

import { EyeIcon, FlameIcon, GridIcon, InfoIcon, PaperIcon, PersonIcon, SearchIcon } from './Icons'

// Six places, each a page a reader can name. Sources is new in this version: who
// Newseye reads, and what each outlet has given it.
const NAV = [
  { to: '/', label: 'Stories', icon: GridIcon, end: true },
  { to: '/contested', label: 'Contested', icon: FlameIcon },
  { to: '/people', label: 'People', icon: PersonIcon },
  { to: '/sources', label: 'Sources', icon: PaperIcon },
  { to: '/search', label: 'Search', icon: SearchIcon },
  { to: '/#about', label: 'How it works', icon: InfoIcon, plain: true },
] as const

function Rail() {
  return (
    <aside className="rail">
      <NavLink to="/" className="brand" viewTransition aria-label="Newseye, all stories">
        <span className="glyph"><EyeIcon /></span>
        <span>
          <b>Newseye</b>
          <small>Kenyan news compared</small>
        </span>
      </NavLink>
      <div>
        <p className="rlabel">Browse</p>
        <nav aria-label="Main">
          {NAV.map(({ to, label, icon: Icon, ...rest }) => (
            <NavLink key={label} to={to} viewTransition end={'end' in rest}
              className={({ isActive }) => (isActive && !('plain' in rest) ? 'on' : undefined)}>
              <span className="ico"><Icon /></span>
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </aside>
  )
}

function TopBar() {
  const location = useLocation()
  // the search page has its own, larger box
  if (location.pathname === '/search') return <div className="topbar" />
  return (
    <div className="topbar">
      <Form className="search" action="/search" role="search">
        <SearchIcon />
        <input type="search" name="q" placeholder="Search every article by meaning"
          aria-label="Search every article by meaning" autoComplete="off" minLength={2} maxLength={200} />
      </Form>
    </div>
  )
}

/** A thin bar across the top while the next page's data is on its way. */
function Progress() {
  const navigation = useNavigation()
  const busy = navigation.state !== 'idle'
  return (
    <div className={`progress${busy ? ' on' : ''}`} role="progressbar" aria-hidden={!busy}
      aria-label="Loading" aria-busy={busy}>
      <span />
    </div>
  )
}

export function Layout() {
  return (
    <div className="app">
      <Rail />
      <div className="main">
        <Progress />
        <TopBar />
        <main className="content" id="content">
          <Outlet />
        </main>
      </div>
      <ScrollRestoration />
    </div>
  )
}
