import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet'
import api from '../../api'
import useWebSocket from '../../useWebSocket'
import { sosIcon, missingIcon, policeIcon } from '../../components/mapIcons'
import { SeverityBadge, StatusBadge, Card } from '../../components/ui.jsx'
import { DEFAULT_MAP, loadMapConfig } from '../../config'
import TouristIdScanner from '../../components/TouristIdScanner.jsx'

// A responder's worklist: incidents assigned to the unit they represent.
// Essential tourist info + a map pin per incident, with quick
// Acknowledge/Resolve actions -- no admin-only capabilities (zone editing,
// audit log, etc.) are reachable from here.
export default function ResponderConsole() {
  const [incidents, setIncidents] = useState([])
  const [tourists, setTourists] = useState({})
  const [mapCfg, setMapCfg] = useState(DEFAULT_MAP)
  const [scanOpen, setScanOpen] = useState(false)

  const load = async () => {
    const { data } = await api.get('/incidents/mine')
    setIncidents(data)
    const missing = data
      .map((i) => i.tourist_id)
      .filter((id) => id != null && !(id in tourists))
    if (missing.length) {
      const fetched = await Promise.all(
        missing.map((id) => api.get(`/tourists/${id}`).then((r) => [id, r.data]).catch(() => [id, null]))
      )
      setTourists((prev) => ({ ...prev, ...Object.fromEntries(fetched) }))
    }
  }

  useEffect(() => {
    load()
    loadMapConfig((p) => api.get(p)).then(setMapCfg)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useWebSocket((ev) => { if (ev.event === 'incident') load() })

  const acknowledge = async (id) => {
    await api.post(`/incidents/${id}/acknowledge`)
    load()
  }

  const resolve = async (id) => {
    await api.patch(`/incidents/${id}`, { status: 'resolved', note: 'Resolved by responder' })
    load()
  }

  const pins = incidents.filter((i) => i.lat != null && i.lng != null)

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold text-slate-800 dark:text-slate-100">My Assigned Incidents</h2>

      <div>
        <button onClick={() => setScanOpen((o) => !o)}
          className="w-full text-sm font-semibold text-sky-700 dark:text-sky-400 bg-sky-50 dark:bg-sky-900/30 rounded-xl py-2">
          {scanOpen ? 'Hide Tourist ID scanner ▲' : '🪪 Scan Tourist Safety ID'}
        </button>
        {scanOpen && (
          <div className="mt-3">
            <TouristIdScanner />
          </div>
        )}
      </div>

      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm overflow-hidden" style={{ height: 320 }}>
        <MapContainer center={mapCfg.center} zoom={mapCfg.zoom} style={{ height: '100%', width: '100%' }} className="map-ops-dark">
          <TileLayer attribution="&copy; OpenStreetMap"
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          {pins.map((i) => (
            <Marker key={i.id} position={[i.lat, i.lng]}
              icon={i.type === 'missing_person' ? missingIcon : i.type === 'sos' ? sosIcon : policeIcon}>
              <Popup>
                <b>Incident #{i.id}</b> ({i.type})<br />
                {tourists[i.tourist_id]?.full_name || 'Unknown tourist'}
              </Popup>
            </Marker>
          ))}
        </MapContainer>
      </div>

      <div className="space-y-3">
        {incidents.length === 0 && (
          <Card><div className="text-slate-400 text-sm">No incidents currently assigned to your unit.</div></Card>
        )}
        {incidents.map((inc) => {
          const tourist = inc.tourist_id != null ? tourists[inc.tourist_id] : null
          return (
            <div key={inc.id} className="bg-white dark:bg-slate-800 rounded-xl shadow-sm p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="font-semibold">#{inc.id}</span>
                  <span className="capitalize">{inc.type.replace('_', ' ')}</span>
                  <SeverityBadge severity={inc.severity} />
                  <StatusBadge status={inc.status} />
                  {inc.escalation_stage && <StatusBadge status={inc.escalation_stage} />}
                </div>
                <div className="flex items-center gap-2">
                  {inc.status !== 'resolved' && inc.escalation_stage !== 'acknowledged' && (
                    <button onClick={() => acknowledge(inc.id)}
                      className="bg-yellow-500 hover:bg-yellow-600 text-white text-xs font-semibold px-3 py-1.5 rounded-lg">
                      Acknowledge
                    </button>
                  )}
                  {inc.status !== 'resolved' && (
                    <button onClick={() => resolve(inc.id)}
                      className="bg-green-600 hover:bg-green-700 text-white text-xs font-semibold px-3 py-1.5 rounded-lg">
                      Resolve
                    </button>
                  )}
                </div>
              </div>
              <div className="text-sm text-slate-600 dark:text-slate-300 mt-1">{inc.description}</div>
              {tourist && (
                <div className="text-xs text-slate-500 dark:text-slate-400 mt-2">
                  Tourist: <b>{tourist.full_name}</b> · {tourist.phone} · ID {tourist.digital_id}
                </div>
              )}
              <div className="flex flex-wrap gap-x-6 gap-y-1 mt-2 text-xs text-slate-500 dark:text-slate-400">
                <span>Detected: {new Date(inc.detected_at).toLocaleString()}</span>
                {inc.lat != null && <span>Loc: {inc.lat.toFixed(4)}, {inc.lng.toFixed(4)}</span>}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
