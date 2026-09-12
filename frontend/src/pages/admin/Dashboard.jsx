import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, Marker, Popup, Polygon } from 'react-leaflet'
import api from '../../api'
import useWebSocket from '../../useWebSocket'
import { touristIcon, sosIcon, missingIcon, policeIcon, riskColor } from '../../components/mapIcons'
import { Stat, SeverityBadge, bandColor } from '../../components/ui.jsx'
import { DEFAULT_MAP, POLL_INTERVAL_MS, loadMapConfig } from '../../config'
import HeatmapLayer from '../../components/HeatmapLayer.jsx'
import TrajectoryOverlay from '../../components/TrajectoryOverlay.jsx'

export default function Dashboard() {
  const [tourists, setTourists] = useState([])
  const [zones, setZones] = useState([])
  const [units, setUnits] = useState([])
  const [alerts, setAlerts] = useState([])
  const [summary, setSummary] = useState(null)
  const [mapCfg, setMapCfg] = useState(DEFAULT_MAP)
  const [heatPoints, setHeatPoints] = useState([])
  const [showHeatmap, setShowHeatmap] = useState(true)
  const [trajectories, setTrajectories] = useState({})

  const load = async () => {
    const [t, z, u, a, s, hist] = await Promise.all([
      api.get('/tourists'),
      api.get('/zones'),
      api.get('/police-units'),
      api.get('/alerts?limit=30'),
      api.get('/analytics/summary'),
      api.get('/alerts?limit=500'), // wider history, purely for the heatmap
    ])
    setTourists(t.data)
    setZones(z.data)
    setUnits(u.data)
    setAlerts(a.data)
    setSummary(s.data)
    setHeatPoints(
      hist.data.filter((al) => al.lat != null && al.lng != null).map((al) => [al.lat, al.lng, 0.6])
    )

    // Predicted short-horizon path per visible tourist, for the trajectory
    // overlay. Best-effort: a single tourist's forecast failing shouldn't
    // block the rest of the live map from loading.
    const visible = t.data.filter((x) => x.last_lat != null)
    const forecasts = await Promise.all(
      visible.map((x) =>
        api.get(`/tourists/${x.id}/trajectory-forecast`)
          .then((r) => [x.id, r.data.points])
          .catch(() => [x.id, null])
      )
    )
    setTrajectories(Object.fromEntries(forecasts))
  }

  useEffect(() => {
    load()
    loadMapConfig((p) => api.get(p)).then(setMapCfg)
    const iv = setInterval(load, POLL_INTERVAL_MS)
    return () => clearInterval(iv)
  }, [])

  const { connected } = useWebSocket((ev) => {
    if (ev.event === 'alert') {
      setAlerts((prev) => [{ ...ev, created_at: ev.created_at || new Date().toISOString() }, ...prev].slice(0, 40))
      if (ev.lat != null && ev.lng != null) {
        setHeatPoints((prev) => [...prev, [ev.lat, ev.lng, 0.6]])
      }
    }
    if (ev.event === 'location') {
      setTourists((prev) => prev.map((t) =>
        t.id === ev.tourist_id ? { ...t, last_lat: ev.lat, last_lng: ev.lng, safety_score: ev.safety_score, status: ev.status } : t))
    }
    if (ev.event === 'incident') load()
  })

  const iconFor = (t) => t.status === 'sos' ? sosIcon : t.status === 'missing' ? missingIcon : touristIcon(t.safety_score)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-slate-800 dark:text-slate-100">Live Operations</h2>
        <div className="flex items-center gap-4 text-sm">
          <label className="flex items-center gap-1.5 cursor-pointer select-none">
            <input type="checkbox" checked={showHeatmap} onChange={(e) => setShowHeatmap(e.target.checked)} />
            Alert heatmap
          </label>
          <div className="flex items-center gap-2">
            <span className={`w-2.5 h-2.5 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'}`}></span>
            {connected ? 'Live feed connected' : 'Reconnecting…'}
          </div>
        </div>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <Stat label="Tourists" value={summary.total_tourists} />
          <Stat label="Active" value={summary.active_tourists} accent="text-green-600" />
          <Stat label="SOS Active" value={summary.sos_active} accent="text-red-600" />
          <Stat label="Missing" value={summary.missing} accent="text-purple-600" />
          <Stat label="Open Incidents" value={summary.open_incidents} accent="text-orange-600" />
          <Stat label="Avg Score" value={summary.avg_safety_score} />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-white dark:bg-slate-800 rounded-xl shadow-sm overflow-hidden" style={{ height: 520 }}>
          <MapContainer center={mapCfg.center} zoom={mapCfg.zoom} style={{ height: '100%', width: '100%' }} className="map-ops-dark">
            <TileLayer
              attribution='&copy; OpenStreetMap'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {zones.map((z) => (
              <Polygon key={z.id} positions={z.polygon}
                pathOptions={{ color: riskColor[z.risk_level], fillOpacity: 0.18, weight: 2 }}>
                <Popup>
                  <b>{z.name}</b><br />Risk: {z.risk_level}<br />
                  Crime index: {z.crime_index}<br />
                  <span className="text-xs text-slate-500">{z.source === 'auto' ? 'DBSCAN-discovered' : 'manual'}</span>
                </Popup>
              </Polygon>
            ))}
            {/* real incident/alert density heatmap, not a fixed-radius zone approximation */}
            {showHeatmap && heatPoints.length > 0 && <HeatmapLayer points={heatPoints} />}
            {units.map((u) => (
              <Marker key={`u${u.id}`} position={[u.lat, u.lng]} icon={policeIcon}>
                <Popup><b>{u.name}</b><br />{u.station}<br />☎ {u.phone}</Popup>
              </Marker>
            ))}
            {tourists.filter((t) => t.last_lat).map((t) => (
              <Marker key={t.id} position={[t.last_lat, t.last_lng]} icon={iconFor(t)}>
                <Popup>
                  <b>{t.full_name}</b> <span className="text-xs">({t.status})</span><br />
                  ID: {t.digital_id}<br />
                  Safety: <b style={{ color: bandColor(t.safety_score) }}>{t.safety_score}</b>
                </Popup>
              </Marker>
            ))}
            {tourists.filter((t) => t.last_lat).map((t) => (
              <TrajectoryOverlay key={`traj${t.id}`} points={trajectories[t.id]} />
            ))}
          </MapContainer>
        </div>

        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm flex flex-col" style={{ height: 520 }}>
          <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-700 font-semibold text-slate-800 dark:text-slate-100 flex items-center justify-between gap-2">
            <span>Live Alert Feed</span>
            <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded-full">{alerts.length}</span>
          </div>
          <div className="flex-1 overflow-y-auto divide-y divide-slate-100">
            {alerts.length === 0 && <div className="p-4 text-sm text-slate-400">No alerts yet.</div>}
            {alerts.map((a, i) => (
              <div key={a.id || i} className="px-4 py-2.5 hover:bg-slate-50">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium capitalize">{a.type?.replace('_', ' ')}</span>
                  <SeverityBadge severity={a.severity} />
                </div>
                <div className="text-xs text-slate-600 mt-0.5">{a.message}</div>
                <div className="text-[10px] text-slate-400 mt-0.5">
                  {a.created_at ? new Date(a.created_at).toLocaleTimeString() : ''}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
