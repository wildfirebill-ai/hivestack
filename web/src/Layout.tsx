import { NavLink, Outlet } from 'react-router-dom'
import { clearToken } from './api'

const links = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/chat', label: 'Chat' },
  { to: '/agents', label: 'Agents' },
  { to: '/workflows', label: 'Workflows' },
  { to: '/boards', label: 'Boards' },
  { to: '/memory', label: 'Memory' },
  { to: '/skills', label: 'Skills' },
  { to: '/studio', label: 'Studio' },
  { to: '/comms', label: 'Comms' },
  { to: '/aiops', label: 'AIOps' },
  { to: '/governance', label: 'Governance' },
  { to: '/economy', label: 'Economy' },
  { to: '/settings', label: 'Settings' },
]

export default function Layout() {
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">hivestack</div>
        <nav>
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} end={l.end} className="nav-link">
              {l.label}
            </NavLink>
          ))}
        </nav>
        <button
          className="logout"
          onClick={() => {
            clearToken()
            window.location.hash = '#/login'
          }}
        >
          Log out
        </button>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}