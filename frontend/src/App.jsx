import { useEffect } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from './auth.jsx'
import { RTL_LANGUAGES } from './i18n.js'
import Login from './pages/Login.jsx'
import Register from './pages/Register.jsx'
import ForgotPassword from './pages/ForgotPassword.jsx'
import GuardianView from './pages/GuardianView.jsx'
import AdminLayout from './pages/admin/AdminLayout.jsx'
import Dashboard from './pages/admin/Dashboard.jsx'
import TouristSearch from './pages/admin/TouristSearch.jsx'
import Zones from './pages/admin/Zones.jsx'
import Incidents from './pages/admin/Incidents.jsx'
import PoliceNetwork from './pages/admin/PoliceNetwork.jsx'
import LiveEmergencies from './pages/admin/LiveEmergencies.jsx'
import Analytics from './pages/admin/Analytics.jsx'
import Devices from './pages/admin/Devices.jsx'
import AuditLog from './pages/admin/AuditLog.jsx'
import TouristApp from './pages/tourist/TouristApp.jsx'
import ResponderLayout from './pages/responder/ResponderLayout.jsx'
import ResponderConsole from './pages/responder/ResponderConsole.jsx'

function Protected({ role, children }) {
  const { user, ready } = useAuth()
  // While the silent refresh against the httpOnly cookie is in flight (see
  // auth.jsx), a rehydrated `user` is only a hint -- rendering the
  // redirect-to-login too early would flash a logged-out screen on every
  // hard reload even for a valid session.
  if (!ready) return null
  if (!user) return <Navigate to="/login" replace />
  const allowed = Array.isArray(role) ? role.includes(user.role) : user.role === role
  if (role && !allowed) return <Navigate to="/" replace />
  return children
}

// The app opens straight into the login screen -- no marketing/landing page
// in front of it. A logged-in user hitting "/" (or anything unmatched, via
// the catch-all route below) still lands on their own console.
function Home() {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  if (user.role === 'admin') return <Navigate to="/admin" replace />
  if (user.role === 'responder') return <Navigate to="/responder" replace />
  return <Navigate to="/app" replace />
}

// RTL only applies to the tourist-facing screens (this app's translated
// surface) -- the admin/responder consoles are untranslated and used by
// Indian police operators, so flipping their layout would be actively
// wrong, not just unnecessary. See i18n.js:RTL_LANGUAGES and i18n.rtl.test.js.
function useDocumentDirection() {
  const { i18n } = useTranslation()
  const location = useLocation()

  useEffect(() => {
    const lang = i18n.resolvedLanguage || i18n.language
    const isAdminRoute = location.pathname.startsWith('/admin') || location.pathname.startsWith('/responder')
    const rtl = RTL_LANGUAGES.includes(lang) && !isAdminRoute
    document.documentElement.dir = rtl ? 'rtl' : 'ltr'
    document.documentElement.lang = lang
  }, [i18n.resolvedLanguage, i18n.language, location.pathname])
}

export default function App() {
  useDocumentDirection()
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/guardian/:token" element={<GuardianView />} />
      <Route path="/" element={<Home />} />

      <Route path="/admin" element={<Protected role="admin"><AdminLayout /></Protected>}>
        <Route index element={<Dashboard />} />
        <Route path="tourists" element={<TouristSearch />} />
        <Route path="zones" element={<Zones />} />
        <Route path="incidents" element={<Incidents />} />
        <Route path="police-network" element={<PoliceNetwork />} />
        <Route path="live-emergencies" element={<LiveEmergencies />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="devices" element={<Devices />} />
        <Route path="audit" element={<AuditLog />} />
      </Route>

      <Route path="/app" element={<Protected role="tourist"><TouristApp /></Protected>} />

      <Route path="/responder" element={<Protected role="responder"><ResponderLayout /></Protected>}>
        <Route index element={<ResponderConsole />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
