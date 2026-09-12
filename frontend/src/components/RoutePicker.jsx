import { useState } from 'react'
import { Polyline, CircleMarker, useMapEvents } from 'react-leaflet'
import api from '../api'
import { riskColor } from './mapIcons'

// Shared state for the safe-route picker, split across two rendering sites:
// `RouteLayer` (map children -- click capture + polylines, must live inside
// a MapContainer) and the default-exported `RoutePicker` (the outside-map
// control panel), matching the existing pattern of keeping plain HTML
// controls outside MapContainer (see Zones.jsx) while only Leaflet layers go
// inside it. Both pieces are driven by this one hook so TouristApp only has
// to wire a single instance of state.
export function useRoutePicker(tid) {
  const [dest, setDest] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const pick = (p) => { setDest(p); setResult(null); setError(null) }

  const findRoute = async () => {
    if (!dest) return
    setLoading(true)
    setError(null)
    try {
      const { data } = await api.get(`/tourists/${tid}/route-recommendation`, {
        params: { dest_lat: dest[0], dest_lng: dest[1] },
      })
      setResult(data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not find a route')
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  const reset = () => { setDest(null); setResult(null); setError(null) }

  return { dest, result, error, loading, pick, findRoute, reset }
}

// Map layer: click-to-pick-destination marker + candidate route polylines,
// colored by risk level with the recommended one drawn thicker. Renders
// nothing when there's no destination/result yet. Uses the same hand-rolled
// click-capture pattern as Zones.jsx's DrawCapture.
export function RouteLayer({ active, dest, result, onPick }) {
  useMapEvents({
    click(e) {
      if (active) onPick([e.latlng.lat, e.latlng.lng])
    },
  })

  return (
    <>
      {dest && (
        <CircleMarker center={dest} radius={7}
          pathOptions={{ color: '#0284c7', fillColor: '#0284c7', fillOpacity: 0.9 }} />
      )}
      {result?.candidates?.map((c, i) => {
        const isRecommended = c === result.recommended
        return (
          <Polyline
            key={i}
            positions={c.points}
            className={isRecommended ? 'route-recommended' : 'route-candidate'}
            pathOptions={{
              color: riskColor[c.risk_level] || riskColor.medium,
              weight: isRecommended ? 6 : 3,
              opacity: isRecommended ? 0.95 : 0.6,
              dashArray: isRecommended ? null : '4 6',
            }}
          />
        )
      })}
    </>
  )
}

// Outside-map control panel: toggle, destination readout, "Find safe route"
// button, and the recommendation summary. `state` is a `useRoutePicker(tid)`
// instance shared with the `RouteLayer` rendered inside the map.
export default function RoutePicker({ active, onToggle, state }) {
  const { dest, result, error, loading, findRoute, reset } = state

  if (!active) return null

  return (
    <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm p-4 text-sm space-y-2">
      <div className="flex items-center justify-between">
        <div className="font-medium text-slate-900 dark:text-slate-100">Safe route</div>
        <button onClick={onToggle} className="text-xs text-slate-500 dark:text-slate-400">Close</button>
      </div>
      <div className="text-xs text-slate-500 dark:text-slate-400">
        {dest ? `Destination: ${dest[0].toFixed(4)}, ${dest[1].toFixed(4)}` : 'Tap the map to choose a destination'}
      </div>
      <div className="flex gap-2">
        <button onClick={findRoute} disabled={!dest || loading}
          className="bg-sky-600 hover:bg-sky-700 disabled:opacity-40 text-white text-xs font-semibold px-3 py-1.5 rounded-lg">
          {loading ? 'Finding…' : 'Find safe route'}
        </button>
        <button onClick={reset} disabled={!dest}
          className="bg-slate-100 hover:bg-slate-200 disabled:opacity-40 text-xs px-3 py-1.5 rounded-lg">
          Reset
        </button>
      </div>
      {error && <div className="text-xs text-red-600">{error}</div>}
      {result && (
        <div className="text-xs text-slate-500 dark:text-slate-400 space-y-1">
          <div>
            Recommended: {result.recommended.length_km} km, risk level{' '}
            <span className="font-semibold">{result.recommended.risk_level}</span>
          </div>
          <div className="italic">Approximate route, not turn-by-turn navigation.</div>
        </div>
      )}
    </div>
  )
}
