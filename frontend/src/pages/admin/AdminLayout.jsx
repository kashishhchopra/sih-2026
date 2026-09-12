import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../../auth.jsx'
import ThemeToggle from '../../components/ThemeToggle.jsx'
import CopilotChat from '../../components/CopilotChat.jsx'

const links = [
  { to: '/admin', label: 'Live Dashboard', end: true, icon: '🗺️' },
  { to: '/admin/tourists', label: 'Tourists', icon: '🧳' },
  { to: '/admin/zones', label: 'Zones', icon: '🗺️' },
  { to: '/admin/incidents', label: 'Incidents', icon: '🚨' },
  { to: '/admin/police-network', label: 'Police Network', icon: '🚓' },
  { to: '/admin/live-emergencies', label: 'Live Emergencies', icon: '🚨' },
  { to: '/admin/analytics', label: 'Analytics', icon: '📊' },
  { to: '/admin/devices', label: 'Devices', icon: '⌚' },
  { to: '/admin/audit', label: 'Audit Log', icon: '🔐' },
]

export default function AdminLayout() {
  const { user, logout } = useAuth()
  const nav = useNavigate()
  return (
    <div data-role-theme="admin" className="theme-surface min-h-screen flex flex-col">
      <header className="bg-slate-900 text-white px-4 py-3 flex items-center justify-between border-b border-sky-900/60">
        <div className="flex items-center gap-2">
          <span className="text-xl">🛡️</span>
          <span className="font-bold tracking-tight">MUSAFIR Control Room</span>
        </div>
        <nav className="hidden md:flex gap-1 overflow-x-auto min-w-0">
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} end={l.end}
              className={({ isActive }) =>
                `px-3 py-1.5 rounded-lg text-sm whitespace-nowrap shrink-0 ${isActive ? 'bg-sky-600' : 'hover:bg-slate-700'}`}>
              <span className="mr-1">{l.icon}</span>{l.label}
            </NavLink>
          ))}
        </nav>
        <div className="flex items-center gap-3 text-sm">
          <span className="text-slate-300 hidden sm:inline">{user?.full_name}</span>
          <ThemeToggle />
          <button onClick={() => { logout(); nav('/login') }}
            className="bg-slate-700 hover:bg-slate-600 px-3 py-1 rounded-lg">Logout</button>
        </div>
      </header>

      <nav className="md:hidden flex gap-1 bg-slate-800 px-2 py-2 overflow-x-auto">
        {links.map((l) => (
          <NavLink key={l.to} to={l.to} end={l.end}
            className={({ isActive }) =>
              `px-3 py-1.5 rounded-lg text-xs whitespace-nowrap ${isActive ? 'bg-sky-600 text-white' : 'text-slate-200'}`}>
            {l.icon} {l.label}
          </NavLink>
        ))}
      </nav>

      <main className="flex-1 p-4 max-w-[1400px] w-full mx-auto">
        <Outlet />
      </main>

      <CopilotChat endpoint="/copilot/ask" title="AI Safety Copilot"
        placeholder="e.g. why was tourist 104 flagged?"
        suggestions={[
          'Which tourists are at risk?',
          'How many active alerts?',
          'How many open incidents?',
        ]} />
    </div>
  )
}
