import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { MapContainer, TileLayer, Marker } from 'react-leaflet'
import api from '../api'
import { bandColor, bandLabel } from '../components/ui.jsx'
import { touristIcon } from '../components/mapIcons'

const POLL_MS = 10000

// Trip Guardian's own read-only view: no login, just the token in the URL.
// Polls the public GET /guardian/{token} endpoint (app/api/guardian.py).
export default function GuardianView() {
  const { token } = useParams()
  const [state, setState] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    const load = () => api.get(`/guardian/${token}`)
      .then((r) => { setState(r.data); setError(null) })
      .catch((e) => setError(e.response?.data?.detail || 'This link is invalid or has expired.'))
    load()
    const iv = setInterval(load, POLL_MS)
    return () => clearInterval(iv)
  }, [token])

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-100 dark:bg-slate-900 p-4">
        <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-xl p-8 max-w-sm text-center">
          <div className="text-4xl mb-2">🔒</div>
          <p className="text-slate-600 dark:text-slate-300">{error}</p>
        </div>
      </div>
    )
  }

  if (!state) return <div className="min-h-screen flex items-center justify-center text-slate-400">Loading…</div>

  const hasLocation = state.last_lat != null && state.last_lng != null

  return (
    <div className="min-h-screen bg-slate-100 dark:bg-slate-900 pb-8">
      <header className="bg-sky-600 text-white px-4 py-4 text-center">
        <div className="text-xs opacity-80">Trip Guardian view for {state.guardian_name}</div>
        <div className="text-xl font-bold">{state.tourist_name}</div>
      </header>

      <div className="max-w-md mx-auto p-4 space-y-4">
        {state.status === 'sos' && (
          <div className="bg-red-600 text-white rounded-xl p-4 text-center font-bold sos-pulse">
            🚨 {state.tourist_name} has triggered an SOS
          </div>
        )}
        {state.status === 'missing' && (
          <div className="bg-purple-600 text-white rounded-xl p-4 text-center font-bold">
            ⚠ {state.tourist_name} has been reported missing
          </div>
        )}

        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm p-4 flex items-center justify-between">
          <div>
            <div className="text-sm text-slate-500 dark:text-slate-400">Safety score</div>
            <div className="text-2xl font-bold" style={{ color: bandColor(state.safety_score) }}>
              {Math.round(state.safety_score)} <span className="text-sm font-normal">({bandLabel(state.safety_score)})</span>
            </div>
          </div>
          <div className="text-right text-xs text-slate-400">
            {!state.trip_active && <div className="text-orange-500 font-semibold">Trip not currently active</div>}
            {state.last_seen && <div>Last seen {new Date(state.last_seen).toLocaleString()}</div>}
          </div>
        </div>

        {hasLocation && (
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm overflow-hidden" style={{ height: 300 }}>
            <MapContainer center={[state.last_lat, state.last_lng]} zoom={13} style={{ height: '100%' }}>
              <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OSM" />
              <Marker position={[state.last_lat, state.last_lng]} icon={touristIcon(state.safety_score)} />
            </MapContainer>
          </div>
        )}
        {!hasLocation && (
          <div className="text-center text-sm text-slate-400 py-6">No location shared yet.</div>
        )}

        <div className="text-center text-xs text-slate-400">
          This page refreshes automatically every {POLL_MS / 1000}s. You were given
          this link by {state.tourist_name} — it shows only their live safety
          status, nothing else.
        </div>
      </div>
    </div>
  )
}
