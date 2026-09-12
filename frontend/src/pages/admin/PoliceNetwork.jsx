import { useEffect, useMemo, useRef, useState } from 'react'
import { MapContainer, TileLayer, Marker, Polygon, Polyline, Popup, useMap } from 'react-leaflet'
import { useNavigate } from 'react-router-dom'
import api from '../../api'
import useWebSocket from '../../useWebSocket'
import { Card, Stat } from '../../components/ui.jsx'
import { touristIcon, sosIcon, stationIcon, cameraIcon, centralIcon, riskColor } from '../../components/mapIcons'
import { DEFAULT_MAP, loadMapConfig } from '../../config'
import CctvNetworkPanel from '../../components/CctvNetworkPanel.jsx'
import { relativeTime } from '../../lib/relativeTime'

// ---------------------------------------------------------------- demo data
// The backend tracks named units (PoliceUnit) and real zone/camera/tourist
// counts, but not a station's full roster -- "officers" and "active units"
// here are a stable, per-station operational estimate for the demo, not a
// live headcount. Everything else on this page (stations, zones, incidents,
// cameras, tourists, forwarding) is real data from the API.
const DEMO_META = {
  'City Central PS': { officers: 32, activeUnits: 12 },
  'Riverside PS': { officers: 22, activeUnits: 9 },
  'Market PS': { officers: 28, activeUnits: 14 },
  'Hillside Outpost': { officers: 14, activeUnits: 6 },
}

function demoMetaFor(station) {
  if (DEMO_META[station.name]) return DEMO_META[station.name]
  const seed = (station.id * 2654435761) % 97
  return { officers: 14 + (seed % 20), activeUnits: 5 + (seed % 10) }
}

function polygonCentroid(polygon) {
  if (!polygon || polygon.length === 0) return null
  const lat = polygon.reduce((s, p) => s + p[0], 0) / polygon.length
  const lng = polygon.reduce((s, p) => s + p[1], 0) / polygon.length
  return [lat, lng]
}

// Station operational status derives from its real open/critical incident
// count (from /police-network/dashboard) -- red only ever means an actual
// emergency, per the control-room colour convention used across the app.
function stationStatus(entry, simCritical) {
  if (simCritical) return 'critical'
  if (entry.critical_incidents > 0) return 'critical'
  if (entry.open_incidents > 0) return 'caution'
  return 'online'
}

const STATUS_META = {
  online: { dot: 'bg-green-500', text: 'text-green-600 dark:text-green-400', label: 'ONLINE' },
  caution: { dot: 'bg-yellow-500', text: 'text-yellow-600 dark:text-yellow-400', label: 'RESPONDING' },
  critical: { dot: 'bg-red-500', text: 'text-red-600 dark:text-red-400', label: 'EMERGENCY' },
}

// Disaster & Weather Monitoring -- same hazard-icon/severity convention
// DisasterBanner.jsx uses on the tourist side, kept in sync deliberately
// (both read the same real DisasterAdvisory data, just via different
// endpoints -- see services/disaster.py).
const HAZARD_ICON = {
  flood: '🌊', landslide: '⛰️', earthquake: '🌍', storm: '⛈️',
  heavy_rain: '🌧️', thunderstorm: '🌩️', extreme_heat: '🔥',
  extreme_cold: '❄️', dense_fog: '🌫️', tsunami: '🌊', cyclone: '🌪️',
}
const DISASTER_SEVERITY_CLS = {
  critical: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  high: 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
  medium: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
  low: 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300',
}

function StatusDot({ status }) {
  const m = STATUS_META[status] || STATUS_META.online
  return <span className={`inline-block w-2 h-2 rounded-full ${m.dot} ${status === 'critical' ? 'sos-pulse' : ''}`} />
}

// Recentres the shared map imperatively when a zone/station is selected
// elsewhere on the page -- must live inside <MapContainer/> to reach useMap().
function FlyTo({ target }) {
  const map = useMap()
  useEffect(() => {
    if (target) map.flyTo(target, Math.max(map.getZoom(), 14), { duration: 0.8 })
  }, [target, map])
  return null
}

const FLOW_STEPS = ['Location', 'Zone', 'Station', 'Central', 'Network', 'Response']

function FlowBreadcrumb() {
  return (
    <div className="flex items-center gap-1.5 overflow-x-auto text-[11px] font-semibold uppercase tracking-wide whitespace-nowrap py-1">
      {FLOW_STEPS.map((step, i) => (
        <div key={step} className="flex items-center gap-1.5">
          <span className="px-2 py-1 rounded-md bg-slate-100 dark:bg-slate-700/70 text-slate-600 dark:text-slate-300">
            {step}
          </span>
          {i < FLOW_STEPS.length - 1 && <span className="text-slate-400 dark:text-slate-600">→</span>}
        </div>
      ))}
    </div>
  )
}

const SIM_STAGES = [
  'Tourist SOS raised',
  'Zone identified',
  'Station notified',
  'Central Dashboard updated',
  'Nearest unit dispatched',
]

export default function PoliceNetwork() {
  const nav = useNavigate()
  const [dashboard, setDashboard] = useState(null)
  const [stations, setStations] = useState([])
  const [zones, setZones] = useState([])
  const [density, setDensity] = useState([])
  const [units, setUnits] = useState([])
  const [tourists, setTourists] = useState([])
  const [cameras, setCameras] = useState([])
  const [mapCfg, setMapCfg] = useState(DEFAULT_MAP)
  const [error, setError] = useState(null)
  // Disaster & Weather Monitoring: GET /police-network/disaster-summary --
  // the same real, database-backed DisasterAdvisory data the tourist
  // dashboard reads (see services/disaster.py), enriched with affected
  // tourist counts and the responsible station. `disastersError` is kept
  // separate from the main `error` state so an unrelated hiccup fetching
  // this doesn't blank out the rest of an otherwise-working dashboard.
  const [disasters, setDisasters] = useState([])
  const [disastersLoading, setDisastersLoading] = useState(true)
  const [disastersError, setDisastersError] = useState(false)

  const [focusTarget, setFocusTarget] = useState(null)
  const [highlightStationId, setHighlightStationId] = useState(null)
  // Police Station Resource Fallback: ranked "who responds here" order for
  // whatever location is currently focused (see backend
  // services/police_network.py:rank_stations_for_point).
  const [fallback, setFallback] = useState([])
  const [detailStation, setDetailStation] = useState(null)
  const [contactStation, setContactStation] = useState(null)
  const [contactConnected, setContactConnected] = useState(false)
  // CCTV console state. `cctvCameras` are the records the CCTV Network
  // panel loaded from /api/cctv (they carry live connection state and the
  // resolved station); the map reuses them so its markers and the console
  // can select each other. Separate from `cameras` above, which is the
  // existing per-station proximity directory and is left untouched.
  const [cctvCameras, setCctvCameras] = useState([])
  const [selectedCameraId, setSelectedCameraId] = useState(null)
  const [openCameraId, setOpenCameraId] = useState(null)
  const [forwardTarget, setForwardTarget] = useState({})
  const [transferReason, setTransferReason] = useState({})
  // Whether "Send Case" also flags the hand-off as sharing live location
  // (services/police_network.py:send_case's `share_live_location` --
  // recorded on the transfer for the audit trail; the location session
  // itself is always tied to the case regardless of this checkbox). Keyed
  // by incident id, default checked.
  const [shareLocation, setShareLocation] = useState({})
  const [caseHistory, setCaseHistory] = useState(null) // { incident, transfers } | null

  const [activity, setActivity] = useState(() => {
    const now = Date.now()
    return [
      { id: 'seed-1', time: new Date(now - 2 * 60000), from: 'Riverside PS', to: 'Central', text: 'Patrol unit status updated' },
      { id: 'seed-2', time: new Date(now - 4 * 60000), from: 'Central', to: 'Market PS', text: 'CCTV feed requested' },
      { id: 'seed-3', time: new Date(now - 6 * 60000), from: 'Hillside Outpost', to: 'Central', text: 'Incident case updated' },
      { id: 'seed-4', time: new Date(now - 8 * 60000), from: 'Central', to: 'Riverside PS', text: 'Tourist location shared' },
    ]
  })
  const [sim, setSim] = useState(null) // { touristId, stationId, stationName, zoneName, lat, lng, stage }
  const simTimers = useRef([])

  const pushActivity = (from, to, text) => {
    setActivity((prev) => [{ id: `${Date.now()}-${Math.random()}`, time: new Date(), from, to, text }, ...prev].slice(0, 40))
  }

  const load = () => {
    Promise.all([
      api.get('/police-network/dashboard'),
      api.get('/police-network/stations'),
      api.get('/zones'),
      api.get('/zones/crowd-density'),
      api.get('/police-units'),
      api.get('/tourists'),
    ])
      .then(([d, s, z, dens, u, t]) => {
        setDashboard(d.data)
        setStations(s.data)
        setZones(z.data)
        setDensity(dens.data)
        setUnits(u.data)
        setTourists(t.data)
        setError(null)
      })
      .catch(() => setError('Failed to load the police network dashboard.'))
  }

  useEffect(() => {
    load()
    loadMapConfig((p) => api.get(p)).then(setMapCfg)
    const iv = setInterval(load, 15000)
    return () => { clearInterval(iv); simTimers.current.forEach(clearTimeout) }
  }, [])

  // Case Transfer real-time push (services/police_network.py:send_case
  // broadcasts this over the same admin WebSocket feed every other live
  // dashboard already uses) -- refreshes the dashboard immediately instead
  // of waiting for the next 15s poll.
  useWebSocket((msg) => {
    if (['transfer_accepted', 'incident'].includes(msg.event)) {
      load()
    }
  })

  // Disaster & Weather Monitoring: polls independently of the main
  // dashboard load() above so a hiccup here never blanks the rest of the
  // page. Same 15s cadence as everything else on this dashboard.
  useEffect(() => {
    const loadDisasters = () =>
      api.get('/police-network/disaster-summary')
        .then((r) => { setDisasters(r.data); setDisastersError(false) })
        .catch(() => setDisastersError(true))
        .finally(() => setDisastersLoading(false))
    loadDisasters()
    const iv = setInterval(loadDisasters, 15000)
    return () => clearInterval(iv)
  }, [])

  // Real CCTV coverage near each station, merged/deduped -- the "Nearby
  // CCTV" section and each station's camera count both come from here.
  useEffect(() => {
    if (stations.length === 0) return
    Promise.all(
      stations.map((s) =>
        api.get(`/police-network/cameras/nearby?lat=${s.lat}&lng=${s.lng}&radius_m=3000`)
          .then((r) => r.data).catch(() => [])
      )
    ).then((lists) => {
      const byId = new Map()
      lists.flat().forEach((c) => byId.set(c.id, c))
      setCameras([...byId.values()])
    })
  }, [stations])

  const zoneById = useMemo(() => Object.fromEntries(zones.map((z) => [z.id, z])), [zones])
  // Map viz for Disaster & Weather Monitoring: which zones currently have
  // an active advisory, so their polygon is drawn distinctly (dashed red)
  // rather than the plain risk-level outline every zone always gets.
  const disastersByZone = useMemo(
    () => Object.fromEntries(disasters.map((d) => [d.zone_id, d])), [disasters],
  )
  const densityByZone = useMemo(() => Object.fromEntries(density.map((d) => [d.zone_id, d])), [density])
  const dashByStation = useMemo(
    () => Object.fromEntries((dashboard?.stations || []).map((s) => [s.id, s])), [dashboard]
  )

  const central = useMemo(() => {
    if (stations.length === 0) return null
    const lat = stations.reduce((s, p) => s + p.lat, 0) / stations.length
    const lng = stations.reduce((s, p) => s + p.lng, 0) / stations.length
    return [lat, lng]
  }, [stations])

  // Per-station derived stats: real open/critical cases, cameras and
  // tourists from the API, plus the demo officer/unit roster estimate.
  const statsFor = (station) => {
    const entry = dashByStation[station.id] || { open_incidents: 0, critical_incidents: 0, incident_ids: [], zone_name: null }
    const zone = station.zone_id ? zoneById[station.zone_id] : null
    const simHere = sim && sim.stationId === station.id
    const openCases = entry.open_incidents + (simHere ? 1 : 0)
    const status = stationStatus(entry, simHere)
    const meta = demoMetaFor(station)
    const cameraCount = cameras.filter((c) => c.zone_id === station.zone_id).length
    const touristCount = station.zone_id ? (densityByZone[station.zone_id]?.tourist_count ?? 0) : 0
    const stationUnits = units.filter((u) => u.station === station.name)
    // Police Station Resource Fallback signals -- real capacity from the
    // backend (services/police_network.py), recomputed against the same
    // openCases the rest of this card shows so a simulated incident moves
    // the load bar too.
    const maxCases = entry.max_concurrent_cases ?? 0
    const loadPct = maxCases ? Math.min(100, Math.round((100 * openCases) / maxCases)) : 0
    const hasCapacity = maxCases ? openCases < maxCases : true
    return {
      entry, zone, status, openCases, meta, cameraCount, touristCount, stationUnits,
      maxCases, loadPct, hasCapacity, officers: entry.total_officers ?? meta.officers,
    }
  }

  const onlineCount = stations.filter((s) => statsFor(s).status !== 'critical').length
  const totalActiveUnits = stations.reduce((sum, s) => sum + statsFor(s).meta.activeUnits, 0)
  const totalOpenCases = (dashboard?.total_open_incidents || 0) + (sim ? 1 : 0)

  const loadFallbackFor = (lat, lng) => {
    api.get(`/police-network/fallback-preview?lat=${lat}&lng=${lng}`)
      .then((r) => setFallback(r.data))
      .catch(() => setFallback([]))
  }

  const focusOnStation = (station) => {
    setHighlightStationId(station.id)
    setFocusTarget([station.lat, station.lng])
    loadFallbackFor(station.lat, station.lng)
  }

  // Selecting a zone (its map polygon) previews the fallback order for a
  // point inside it, same as selecting a station -- highlights whichever
  // station currently owns that zone so the two selection paths agree.
  const focusOnZone = (zone) => {
    const centroid = polygonCentroid(zone.polygon)
    if (!centroid) return
    const owner = stations.find((s) => s.zone_id === zone.id)
    setHighlightStationId(owner ? owner.id : null)
    setFocusTarget(centroid)
    loadFallbackFor(centroid[0], centroid[1])
  }

  // Case Transfer: one click, no receiving-station approval step -- the case
  // (and its live-location session, untouched here) moves immediately. See
  // backend services/police_network.py:send_case.
  const sendCase = async (incidentId, fromStationId) => {
    const toStationId = Number(forwardTarget[incidentId])
    if (!toStationId || toStationId === fromStationId) return
    const toStation = stations.find((s) => s.id === toStationId)
    const fromStation = stations.find((s) => s.id === fromStationId)
    try {
      await api.post(`/police-network/incidents/${incidentId}/transfer/send`, {
        to_station_id: toStationId,
        reason: transferReason[incidentId] || 'Sent from Central Safety Dashboard',
        share_live_location: shareLocation[incidentId] ?? true,
      })
      pushActivity(fromStation?.name || 'Station', toStation?.name || 'Station',
        `Case #${incidentId} sent — live tracking continues`)
      setForwardTarget({ ...forwardTarget, [incidentId]: '' })
      setTransferReason({ ...transferReason, [incidentId]: '' })
      load()
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to send the case.')
    }
  }

  const viewCaseHistory = async (incidentId) => {
    try {
      const [inc, transfers] = await Promise.all([
        api.get(`/incidents/${incidentId}`),
        api.get(`/police-network/incidents/${incidentId}/transfers`),
      ])
      setCaseHistory({ incident: inc.data, transfers: transfers.data })
    } catch {
      setError('Failed to load case history.')
    }
  }

  const openContact = (station) => {
    setContactStation(station)
    setContactConnected(false)
    pushActivity('Central', station.name, 'Contact request sent')
    setTimeout(() => setContactConnected(true), 900)
  }

  // Client-side demo only -- does not touch real tourist/incident data.
  // Walks a fake SOS through the exact routing path the backend implements
  // for real (services/police_network.py): zone -> station -> central dashboard.
  const simulateIncident = () => {
    const candidates = (dashboard?.stations || []).filter((s) => s.zone_id)
    if (candidates.length === 0) return
    simTimers.current.forEach(clearTimeout)
    simTimers.current = []

    const target = candidates[Math.floor(Math.random() * candidates.length)]
    const zone = zoneById[target.zone_id]
    const centroid = polygonCentroid(zone?.polygon) || [target.lat, target.lng]
    const touristId = `T-${1000 + Math.floor(Math.random() * 900)}`

    setSim({
      touristId, stationId: target.id, stationName: target.name,
      zoneName: target.zone_name, lat: centroid[0], lng: centroid[1], stage: 0,
    })
    pushActivity(`Tourist ${touristId}`, 'Central', 'SOS button pressed')
    setFocusTarget(centroid)
    loadFallbackFor(centroid[0], centroid[1])

    const steps = [
      { at: 900, run: () => pushActivity('Central', 'System', `Zone resolved: ${zone?.name || target.zone_name}`) },
      { at: 1800, run: () => pushActivity('Central', target.name, `SOS forwarded — tourist ${touristId}`) },
      { at: 2700, run: () => pushActivity(target.name, 'Central', 'Case acknowledged') },
      { at: 3600, run: () => pushActivity(target.name, 'Central', 'Nearest unit dispatched — ETA ~6 min') },
    ]
    steps.forEach((step, i) => {
      simTimers.current.push(setTimeout(() => {
        step.run()
        setSim((prev) => (prev && prev.touristId === touristId ? { ...prev, stage: i + 1 } : prev))
      }, step.at))
    })
  }

  const resolveSimulation = () => {
    if (!sim) return
    pushActivity(sim.stationName, 'Central', 'Incident resolved — unit returning to patrol')
    setSim(null)
  }

  if (error) return <div className="text-red-600 text-sm">{error}</div>
  if (!dashboard) return <div className="text-slate-400 text-sm">Loading network…</div>

  return (
    <div className="space-y-4">
      {/* ---- header / network status ---- */}
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-lg font-bold text-slate-800 dark:text-slate-100">Central Safety Dashboard</h2>
            <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              <StatusDot status={sim ? 'critical' : 'online'} />
              <span className="font-semibold tracking-wide">
                {sim ? 'ACTIVE RESPONSE IN PROGRESS' : 'NETWORK OPERATIONAL'}
              </span>
              <span className="text-slate-400 dark:text-slate-600">·</span>
              <span>Last synchronized {new Date(dashboard.generated_at).toLocaleTimeString()}</span>
            </div>
          </div>
          <FlowBreadcrumb />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="Police Stations" value={stations.length} />
          <Stat label="Online" value={onlineCount} accent="text-green-600" />
          <Stat label="Active Units" value={totalActiveUnits} accent="text-sky-600" />
          <Stat label="Open Cases" value={totalOpenCases}
            accent={totalOpenCases > 0 ? 'text-red-600' : 'text-slate-900 dark:text-slate-100'} />
        </div>

        {dashboard.unassigned_incidents.length > 0 && (
          <div className="text-xs bg-orange-50 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300
                          border border-orange-200 dark:border-orange-800 rounded-lg px-3 py-2">
            ⚠ {dashboard.unassigned_incidents.length} incident(s) fell outside every zone and are not yet
            owned by a station: {dashboard.unassigned_incidents.map((id) => `#${id}`).join(', ')}
          </div>
        )}
      </div>

      {/* ---- main map + zone table (left) / live response + activity (right) ---- */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2 space-y-4">
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm overflow-hidden" style={{ height: 480 }}>
            <MapContainer center={mapCfg.center} zoom={mapCfg.zoom} style={{ height: '100%', width: '100%' }} className="map-ops-dark">
              <TileLayer attribution="&copy; OpenStreetMap"
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
              <FlyTo target={focusTarget} />

              {zones.map((z) => {
                const hazard = disastersByZone[z.id]
                return (
                  <Polygon key={z.id} positions={z.polygon}
                    pathOptions={hazard
                      ? { color: '#dc2626', fillOpacity: 0.2, weight: 2.5, dashArray: '6 6' }
                      : { color: riskColor[z.risk_level], fillOpacity: 0.12, weight: 1.5 }}
                    eventHandlers={{ click: () => focusOnZone(z) }}>
                    <Popup>
                      <b>{z.name}</b><br />Risk: {z.risk_level}
                      {hazard && (
                        <><br />{HAZARD_ICON[hazard.hazard_type] || '⚠️'} <b>{hazard.title || hazard.hazard_type}</b>
                        ({hazard.severity}) — {hazard.affected_tourists} tourist(s) affected</>
                      )}
                    </Popup>
                  </Polygon>
                )
              })}

              {/* hub-and-spoke: every station <-> the Central Safety Dashboard */}
              {central && stations.map((s) => (
                <Polyline key={`hub${s.id}`} positions={[central, [s.lat, s.lng]]}
                  pathOptions={{ color: '#0ea5e9', weight: 2, opacity: 0.6, dashArray: '6 8', className: 'network-line' }} />
              ))}
              {/* peer mesh ring: stations directly interconnected, not just via the hub */}
              {stations.map((s, i) => {
                const next = stations[(i + 1) % stations.length]
                if (!next || stations.length < 2) return null
                return (
                  <Polyline key={`ring${s.id}`} positions={[[s.lat, s.lng], [next.lat, next.lng]]}
                    pathOptions={{ color: '#64748b', weight: 1, opacity: 0.4, dashArray: '2 6' }} />
                )
              })}
              {/* live simulated SOS -> station link */}
              {sim && (
                <Polyline positions={[[sim.lat, sim.lng], (() => {
                  const st = stations.find((s) => s.id === sim.stationId)
                  return st ? [st.lat, st.lng] : [sim.lat, sim.lng]
                })()]} pathOptions={{ color: '#dc2626', weight: 3, opacity: 0.85 }} />
              )}

              {central && (
                <Marker position={central} icon={centralIcon}>
                  <Popup><b>Central Safety Dashboard</b><br />Interconnected police network hub</Popup>
                </Marker>
              )}
              {stations.map((s) => {
                const { status, entry } = statsFor(s)
                return (
                  <Marker key={s.id} position={[s.lat, s.lng]} icon={stationIcon(status)}
                    eventHandlers={{ click: () => focusOnStation(s) }}>
                    <Popup>
                      <b>{s.name}</b><br />
                      Covers: {entry.zone_name || 'unassigned'}<br />
                      {entry.open_incidents} open case(s)
                    </Popup>
                  </Marker>
                )
              })}
              {/* Camera markers are generated from the coordinates the API
                  returns -- never a hardcoded marker list. Prefer the CCTV
                  console's records (they carry live status + station) and
                  fall back to the proximity directory before it loads. */}
              {(cctvCameras.length > 0 ? cctvCameras : cameras).map((c) => (
                <Marker key={`cam${c.id}`} position={[c.lat, c.lng]} icon={cameraIcon}
                  eventHandlers={{ click: () => { setSelectedCameraId(c.id); setOpenCameraId(c.id) } }}>
                  <Popup>
                    <b>{c.label}</b><br />
                    {c.connection ? `Feed: ${c.connection}` : c.status}
                    <br />
                    <button type="button"
                      onClick={() => { setSelectedCameraId(c.id); setOpenCameraId(c.id) }}
                      className="text-sky-600 underline">View feed</button>
                  </Popup>
                </Marker>
              ))}
              {tourists.filter((t) => t.last_lat).map((t) => (
                <Marker key={`t${t.id}`} position={[t.last_lat, t.last_lng]} icon={touristIcon(t.safety_score)}>
                  <Popup><b>{t.full_name}</b><br />{t.status}</Popup>
                </Marker>
              ))}
              {sim && <Marker position={[sim.lat, sim.lng]} icon={sosIcon}>
                <Popup><b>{sim.touristId}</b> — simulated SOS</Popup>
              </Marker>}
            </MapContainer>
          </div>
          <div className="text-[11px] text-slate-400 -mt-2 px-1">
            Click a zone shape or station marker on the map — or a row in Zone Coverage below —
            to preview its Resource Fallback Order.
          </div>

          <Card title="Zone Coverage & Assignment">
            <div className="overflow-x-auto -mx-4 px-4">
              <table className="w-full text-sm min-w-[560px]">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-slate-400 border-b border-slate-100 dark:border-slate-700">
                    <th className="pb-2 pr-2">Zone</th>
                    <th className="pb-2 pr-2">Risk</th>
                    <th className="pb-2 pr-2">Station</th>
                    <th className="pb-2 pr-2 text-right">Tourists</th>
                    <th className="pb-2 pr-2 text-right">Cameras</th>
                    <th className="pb-2 text-right">Cases</th>
                  </tr>
                </thead>
                <tbody>
                  {stations.map((s) => {
                    const st = statsFor(s)
                    return (
                      <tr key={s.id}
                        onClick={() => focusOnStation(s)}
                        className={`cursor-pointer border-b border-slate-50 dark:border-slate-700/50 last:border-0
                          hover:bg-slate-50 dark:hover:bg-slate-700/40 ${highlightStationId === s.id ? 'bg-sky-50 dark:bg-sky-900/20' : ''}`}>
                        <td className="py-2 pr-2 font-medium">{st.zone?.name || '—'}</td>
                        <td className="py-2 pr-2">
                          <span className="inline-flex items-center gap-1.5">
                            <span className="w-2 h-2 rounded-full inline-block" style={{ background: riskColor[st.zone?.risk_level] || '#94a3b8' }} />
                            <span className="capitalize text-xs text-slate-500 dark:text-slate-400">{st.zone?.risk_level || '—'}</span>
                          </span>
                        </td>
                        <td className="py-2 pr-2 text-slate-600 dark:text-slate-300">{s.name}</td>
                        <td className="py-2 pr-2 text-right">{st.touristCount}</td>
                        <td className="py-2 pr-2 text-right">{st.cameraCount}</td>
                        <td className={`py-2 text-right font-semibold ${st.openCases > 0 ? 'text-red-600' : 'text-slate-400'}`}>
                          {st.openCases}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        </div>

        <div className="space-y-4">
          {/* Disaster & Weather Monitoring -- real DisasterAdvisory data
              (services/disaster.py), same source the tourist dashboard
              reads, enriched here with affected-tourist counts and the
              responsible station. */}
          <Card title="Disaster & Weather Monitoring">
            {disastersLoading ? (
              <div className="text-sm text-slate-400">Fetching weather &amp; disaster alerts…</div>
            ) : disastersError ? (
              <div className="text-sm text-red-500">
                Weather &amp; Disaster Alert Service Unavailable
                <button onClick={() => { setDisastersLoading(true); setDisastersError(false) }}
                  className="ml-2 text-sky-600 underline">Retry</button>
              </div>
            ) : disasters.length === 0 ? (
              <div className="text-sm text-slate-400">No active weather or disaster alerts in your area.</div>
            ) : (
              <div className="space-y-2 max-h-[280px] overflow-y-auto">
                {disasters.map((d) => (
                  <div key={d.id} className="border-b border-slate-50 dark:border-slate-700/50 last:border-0 pb-2 last:pb-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium flex items-center gap-1.5 min-w-0">
                        <span>{HAZARD_ICON[d.hazard_type] || '⚠️'}</span>
                        <span className="truncate">{d.title || d.hazard_type}</span>
                      </span>
                      <span className={`text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded-full whitespace-nowrap ${DISASTER_SEVERITY_CLS[d.severity] || DISASTER_SEVERITY_CLS.medium}`}>
                        {d.severity}
                      </span>
                    </div>
                    <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                      📍 {d.zone_name || `Zone #${d.zone_id}`}
                      {d.station_name && <> · 🚓 {d.station_name}</>}
                    </div>
                    <div className="flex items-center justify-between text-[11px] text-slate-400 mt-0.5">
                      <span className={d.affected_tourists > 0 ? 'font-semibold text-orange-600 dark:text-orange-400' : ''}>
                        👥 {d.affected_tourists} affected tourist{d.affected_tourists === 1 ? '' : 's'}
                      </span>
                      <span>{d.source} · {relativeTime(d.issued_at)}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* live response */}
          <Card title="Live Response">
            {sim ? (
              <div className="space-y-3 text-sm">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-xs text-slate-400">Tourist</div>
                    <div className="font-semibold">{sim.touristId}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-xs text-slate-400">Assigned Station</div>
                    <div className="font-semibold">{sim.stationName}</div>
                  </div>
                </div>
                <div className="text-xs text-slate-400">Zone: <span className="text-slate-600 dark:text-slate-300">{sim.zoneName}</span></div>
                <div className="space-y-1 border-l-2 border-slate-200 dark:border-slate-700 pl-3">
                  {SIM_STAGES.map((label, i) => (
                    <div key={label} className={`text-xs flex items-center gap-1.5 ${i <= sim.stage ? 'text-slate-700 dark:text-slate-200 font-medium' : 'text-slate-300 dark:text-slate-600'}`}>
                      <span>{i <= sim.stage ? '✔' : '○'}</span>{label}
                    </div>
                  ))}
                </div>
                <div className="flex items-center justify-between pt-1">
                  <span className="text-xs font-semibold text-yellow-600 dark:text-yellow-400 flex items-center gap-1.5">
                    <StatusDot status="caution" /> RESPONSE IN PROGRESS
                  </span>
                  {sim.stage >= SIM_STAGES.length - 1 && (
                    <button onClick={resolveSimulation}
                      className="text-xs bg-green-600 hover:bg-green-700 text-white font-semibold px-3 py-1 rounded-lg">
                      Mark Resolved
                    </button>
                  )}
                </div>
              </div>
            ) : (
              <div className="space-y-3 text-sm text-center py-2">
                <div className="text-green-600 dark:text-green-400 font-semibold flex items-center justify-center gap-1.5">
                  <StatusDot status="online" /> No active emergency responses
                </div>
                <button onClick={simulateIncident}
                  className="bg-red-600 hover:bg-red-700 text-white text-xs font-semibold px-4 py-2 rounded-lg">
                  🚨 Simulate Incident
                </button>
              </div>
            )}
          </Card>

          {/* resource fallback order for the focused location */}
          <Card title="Resource Fallback Order">
            {fallback.length === 0 ? (
              <div className="text-sm text-slate-400">
                Click a zone or station marker on the map, or a row in Zone Coverage below,
                to see who would take an emergency there.
              </div>
            ) : (
              <div className="space-y-2">
                <div className="text-[11px] text-slate-400">
                  Who takes an emergency at the selected location — and who it falls back to
                  if the first station is overloaded.
                </div>
                {fallback.slice(0, 4).map((f, i) => (
                  <div key={f.station_id} className="flex items-center gap-2 text-xs">
                    <span className={`w-5 text-center font-bold ${i === 0 ? 'text-green-600' : 'text-slate-400'}`}>
                      {i === 0 ? '1' : `${i + 1}`}
                    </span>
                    <span className="flex-1 min-w-0">
                      <span className="font-medium text-slate-700 dark:text-slate-200">{f.name}</span>
                      <span className="text-slate-400"> · {f.distance_km} km</span>
                    </span>
                    <span className={f.has_capacity
                      ? 'text-[11px] text-green-600 whitespace-nowrap'
                      : 'text-[11px] text-red-600 font-semibold whitespace-nowrap'}>
                      {f.open_cases}/{f.max_concurrent_cases} {f.has_capacity ? 'free' : 'FULL'}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* network activity feed */}
          <Card title="Police Network Activity">
            <div className="space-y-2.5 max-h-[360px] overflow-y-auto">
              {activity.map((a) => (
                <div key={a.id} className="text-xs border-b border-slate-50 dark:border-slate-700/50 pb-2 last:border-0 last:pb-0">
                  <div className="flex items-center justify-between text-slate-400">
                    <span>{a.time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                  </div>
                  <div className="font-medium text-slate-700 dark:text-slate-200">
                    {a.from} <span className="text-slate-400">→</span> {a.to}
                  </div>
                  <div className="text-slate-500 dark:text-slate-400">{a.text}</div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>

      {/* ---- station cards ---- */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {stations.map((s) => {
          const st = statsFor(s)
          const meta = STATUS_META[st.status]
          return (
            <div key={s.id}
              className={`bg-white dark:bg-slate-800 rounded-xl shadow-sm border transition
                ${highlightStationId === s.id ? 'border-sky-400 ring-1 ring-sky-300' : 'border-transparent'}`}>
              <div onClick={() => focusOnStation(s)}
                className="cursor-pointer px-4 pt-3 pb-2 border-b border-slate-100 dark:border-slate-700">
                <div className="flex items-center justify-between">
                  <div className="font-bold text-sm text-slate-800 dark:text-slate-100 uppercase tracking-wide">{s.name}</div>
                </div>
                <div className={`text-[11px] font-semibold flex items-center gap-1.5 mt-0.5 ${meta.text}`}>
                  <StatusDot status={st.status} /> {meta.label}
                </div>
              </div>
              <div className="p-4 space-y-2 text-xs text-slate-600 dark:text-slate-300">
                <div>📍 {st.zone?.name || 'No zone assigned'}</div>
                <div>👮 {s.contact_officer || '—'}</div>
                <div className="grid grid-cols-2 gap-y-1.5 pt-1 text-slate-700 dark:text-slate-200">
                  <div>🚓 {st.meta.activeUnits} Active Units</div>
                  <div>📹 {st.cameraCount} Cameras</div>
                  <div>👥 {st.touristCount} Tourists</div>
                  <div className={st.openCases > 0 ? 'text-red-600 font-semibold' : ''}>🚨 {st.openCases} Open Cases</div>
                </div>

                {/* Resource capacity -- a station at 100% gets routed around
                    by the fallback system (services/police_network.py) */}
                {st.maxCases > 0 && (
                  <div className="pt-1">
                    <div className="flex items-center justify-between text-[11px] mb-1">
                      <span className="text-slate-400">Case load</span>
                      <span className={st.hasCapacity ? 'text-slate-500 dark:text-slate-400' : 'text-red-600 font-semibold'}>
                        {st.openCases}/{st.maxCases} {st.hasCapacity ? '' : '· AT CAPACITY'}
                      </span>
                    </div>
                    <div className="h-1.5 w-full rounded-full bg-slate-100 dark:bg-slate-700 overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${
                          !st.hasCapacity ? 'bg-red-500' : st.loadPct >= 60 ? 'bg-yellow-500' : 'bg-green-500'
                        }`}
                        style={{ width: `${Math.max(st.loadPct, 3)}%` }}
                      />
                    </div>
                  </div>
                )}

                <div className="flex gap-2 pt-2">
                  <button onClick={() => setDetailStation(s)}
                    className="flex-1 bg-sky-600 hover:bg-sky-700 text-white text-xs font-semibold py-1.5 rounded-lg">
                    View Station
                  </button>
                  <button onClick={() => openContact(s)}
                    className="flex-1 bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 text-xs font-semibold py-1.5 rounded-lg">
                    Contact
                  </button>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* ---- CCTV surveillance console (real feeds from /api/cctv) ---- */}
      <CctvNetworkPanel
        stations={stations}
        selectedCameraId={selectedCameraId}
        openCameraId={openCameraId}
        onOpenHandled={() => setOpenCameraId(null)}
        onCamerasLoaded={setCctvCameras}
        onFocusCamera={(cam) => { setSelectedCameraId(cam.id); setFocusTarget([cam.lat, cam.lng]) }}
      />

      {/* ---- station detail modal ---- */}
      {detailStation && (() => {
        const s = detailStation
        const st = statsFor(s)
        const stationActivity = activity.filter((a) => a.from === s.name || a.to === s.name).slice(0, 6)
        const stationCameras = cameras.filter((c) => c.zone_id === s.zone_id)
        return (
          <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[2000] p-4"
            onClick={() => setDetailStation(null)}>
            <div className="bg-white dark:bg-slate-800 rounded-2xl w-full max-w-lg max-h-[85vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}>
              <div className="px-5 pt-4 pb-3 border-b border-slate-100 dark:border-slate-700 flex items-center justify-between">
                <div>
                  <div className="font-bold uppercase tracking-wide text-slate-800 dark:text-slate-100">{s.name}</div>
                  <div className={`text-xs font-semibold flex items-center gap-1.5 mt-0.5 ${STATUS_META[st.status].text}`}>
                    <StatusDot status={st.status} /> {STATUS_META[st.status].label}
                  </div>
                </div>
                <button onClick={() => setDetailStation(null)}
                  className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-xl leading-none">✕</button>
              </div>
              <div className="p-5 space-y-4 text-sm">
                <div>
                  <div className="text-xs text-slate-400">Station Commander</div>
                  <div className="font-medium">{s.contact_officer || '—'} · ☎ {s.phone}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-400">Coverage</div>
                  <div className="font-medium">{st.zone?.name || 'No zone assigned'}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-400 mb-1">Operational Statistics</div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="bg-slate-50 dark:bg-slate-700/40 rounded-lg px-3 py-2">Officers <b className="block text-sm">{st.meta.officers}</b></div>
                    <div className="bg-slate-50 dark:bg-slate-700/40 rounded-lg px-3 py-2">Active Units <b className="block text-sm">{st.meta.activeUnits}</b></div>
                    <div className="bg-slate-50 dark:bg-slate-700/40 rounded-lg px-3 py-2">Cameras <b className="block text-sm">{st.cameraCount}</b></div>
                    <div className="bg-slate-50 dark:bg-slate-700/40 rounded-lg px-3 py-2">Tourists in Zone <b className="block text-sm">{st.touristCount}</b></div>
                  </div>
                </div>

                <div>
                  <div className="text-xs text-slate-400 mb-1">
                    Active Incidents
                    <span className="normal-case text-slate-300 dark:text-slate-500"> — send a case directly to
                    another station; live location keeps sharing automatically.</span>
                  </div>
                  {st.entry.incident_ids.length === 0 ? (
                    <div className="text-xs text-slate-400">No active cases.</div>
                  ) : (
                    <div className="space-y-2">
                      {st.entry.incident_ids.map((id) => (
                        <div key={id} className="space-y-1.5 border border-slate-100 dark:border-slate-700 rounded-lg p-2">
                          <div className="flex items-center gap-2 text-xs">
                            <button onClick={() => viewCaseHistory(id)}
                              className="w-14 text-left text-sky-600 hover:underline font-semibold">#{id}</button>
                            <button onClick={() => nav(`/admin/live-emergencies?incident=${id}`)}
                              className="text-[11px] font-semibold text-red-600 hover:underline whitespace-nowrap">
                              📍 View Live Location
                            </button>
                          </div>
                          <div className="flex items-center gap-2 text-xs">
                            <span className="w-14" />
                            <select className="flex-1 border border-slate-300 dark:border-slate-600 dark:bg-slate-700 rounded-lg px-2 py-1"
                              value={forwardTarget[id] || ''}
                              onChange={(e) => setForwardTarget({ ...forwardTarget, [id]: e.target.value })}>
                              <option value="">Send to…</option>
                              {stations.filter((o) => o.id !== s.id).map((o) => (
                                <option key={o.id} value={o.id}>{o.name}</option>
                              ))}
                            </select>
                            <button onClick={() => sendCase(id, s.id)} disabled={!forwardTarget[id]}
                              className="bg-sky-600 hover:bg-sky-700 disabled:opacity-40 text-white font-semibold px-2 py-1 rounded-lg">
                              Send Case
                            </button>
                          </div>
                          {forwardTarget[id] && (
                            <div className="pl-16 space-y-1.5">
                              <input type="text" placeholder="Reason (optional)"
                                className="w-full text-xs border border-slate-200 dark:border-slate-600 dark:bg-slate-700 rounded-lg px-2 py-1"
                                value={transferReason[id] || ''}
                                onChange={(e) => setTransferReason({ ...transferReason, [id]: e.target.value })} />
                              <label className="flex items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
                                <input type="checkbox"
                                  checked={shareLocation[id] ?? true}
                                  onChange={(e) => setShareLocation({ ...shareLocation, [id]: e.target.checked })} />
                                Share Live Location
                              </label>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div>
                  <div className="text-xs text-slate-400 mb-1">Recent Activity</div>
                  {stationActivity.length === 0 ? (
                    <div className="text-xs text-slate-400">No recent network activity.</div>
                  ) : (
                    <div className="space-y-1">
                      {stationActivity.map((a) => (
                        <div key={a.id} className="text-xs text-slate-600 dark:text-slate-300">
                          {a.from} → {a.to}: {a.text}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {stationCameras.length > 0 && (
                  <div>
                    <div className="text-xs text-slate-400 mb-1">Nearby CCTV</div>
                    <div className="flex flex-wrap gap-1.5">
                      {stationCameras.map((c) => (
                        <span key={c.id} className="text-[10px] bg-slate-100 dark:bg-slate-700 px-2 py-1 rounded-full">
                          {c.status === 'active' ? '🟢' : '⚪'} {c.label}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <button onClick={() => setDetailStation(null)}
                  className="w-full bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 text-sm font-semibold py-2 rounded-lg">
                  Close
                </button>
              </div>
            </div>
          </div>
        )
      })()}

      {/* ---- contact modal ---- */}
      {contactStation && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[2000] p-4"
          onClick={() => setContactStation(null)}>
          <div className="bg-white dark:bg-slate-800 rounded-2xl p-6 w-full max-w-xs text-center"
            onClick={(e) => e.stopPropagation()}>
            {!contactConnected ? (
              <>
                <div className="text-sm text-slate-500 dark:text-slate-400 mb-2">Connecting…</div>
                <div className="font-bold text-slate-800 dark:text-slate-100">{contactStation.name}</div>
              </>
            ) : (
              <>
                <div className="text-green-600 dark:text-green-400 font-semibold text-sm mb-1">🟢 Connected</div>
                <div className="font-bold text-slate-800 dark:text-slate-100">{contactStation.name}</div>
                <div className="text-sm text-slate-500 dark:text-slate-400 mt-1">{contactStation.contact_officer}</div>
                <div className="text-sm text-slate-500 dark:text-slate-400">☎ {contactStation.phone}</div>
              </>
            )}
            <button onClick={() => setContactStation(null)}
              className="mt-4 w-full bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 text-sm font-semibold py-2 rounded-lg">
              Close
            </button>
          </div>
        </div>
      )}

      {/* ---- case history modal: incident event log + full transfer history ---- */}
      {caseHistory && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[2000] p-4"
          onClick={() => setCaseHistory(null)}>
          <div className="bg-white dark:bg-slate-800 rounded-2xl w-full max-w-lg max-h-[85vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}>
            <div className="px-5 pt-4 pb-3 border-b border-slate-100 dark:border-slate-700 flex items-center justify-between">
              <div className="font-bold text-slate-800 dark:text-slate-100">Case #{caseHistory.incident.id} History</div>
              <button onClick={() => setCaseHistory(null)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-xl leading-none">✕</button>
            </div>
            <div className="p-5 space-y-4 text-sm">
              <div>
                <div className="text-xs text-slate-400 mb-1">Currently Assigned Station</div>
                <div className="font-medium">
                  {stations.find((s) => s.id === caseHistory.incident.station_id)?.name || 'Unassigned'}
                </div>
              </div>

              <div>
                <div className="text-xs text-slate-400 mb-1">Transfer History</div>
                {caseHistory.transfers.length === 0 ? (
                  <div className="text-xs text-slate-400">No transfers for this case.</div>
                ) : (
                  <div className="space-y-1.5">
                    {caseHistory.transfers.map((t) => {
                      const from = stations.find((s) => s.id === t.from_station_id)
                      const to = stations.find((s) => s.id === t.to_station_id)
                      const badge = {
                        requested: 'text-amber-600', accepted: 'text-green-600',
                        rejected: 'text-red-600', cancelled: 'text-slate-400',
                      }[t.status] || 'text-slate-500'
                      return (
                        <div key={t.id} className="text-xs border-b border-slate-50 dark:border-slate-700/50 pb-1.5 last:border-0">
                          <div className="flex items-center justify-between">
                            <span className="font-medium">{from?.name || 'Control room'} → {to?.name || `Station ${t.to_station_id}`}</span>
                            <span className={`font-bold uppercase ${badge}`}>{t.status}</span>
                          </div>
                          {t.reason && <div className="text-slate-500 dark:text-slate-400">{t.reason}</div>}
                          <div className="text-slate-400">
                            Requested {new Date(t.requested_at).toLocaleString()} by {t.requested_by}
                            {t.responded_at && ` · resolved ${new Date(t.responded_at).toLocaleString()} by ${t.responded_by}`}
                          </div>
                          <div className="text-slate-400">
                            Location Shared: {t.location_shared ? '✓' : '✗'}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>

              <div>
                <div className="text-xs text-slate-400 mb-1">Case Event Log</div>
                <div className="space-y-1">
                  {caseHistory.incident.events.map((e, i) => (
                    <div key={i} className="text-xs text-slate-600 dark:text-slate-300">
                      <span className="text-slate-400">{new Date(e.timestamp).toLocaleTimeString()}</span> — {e.note || e.status}
                    </div>
                  ))}
                </div>
              </div>

              <button onClick={() => setCaseHistory(null)}
                className="w-full bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 text-sm font-semibold py-2 rounded-lg">
                Close
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  )
}
