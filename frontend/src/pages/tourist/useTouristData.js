import { useEffect, useRef, useState } from 'react'
import api from '../../api'
import { pointInPoly, haversineKm } from '../../components/geo'
import { TRACK_INTERVAL_MS, SIMULATE_GPS } from '../../config'
import useGeolocation from '../../hooks/useGeolocation'
import useOnlineStatus from '../../hooks/useOnlineStatus'
import useWebSocket from '../../useWebSocket'
import { enqueueSOS, flushQueue, queueLength } from '../../lib/offlineQueue'
import { useRoutePicker } from '../../components/RoutePicker.jsx'

// All the tourist app's live data + mutations, extracted out of the screen
// component so it's testable without mounting a Leaflet map (there was no
// TouristApp.test.jsx before this -- the whole load/track/SOS pipeline was
// unreachable from a test without a real DOM map). TouristShell and every
// tab consume this via one hook call.
export default function useTouristData(tid) {
  const online = useOnlineStatus()
  const [me, setMe] = useState(null)
  const [score, setScore] = useState(null)
  const [zones, setZones] = useState([])
  const [units, setUnits] = useState([])
  const [trajectory, setTrajectory] = useState([])
  const [riskForecast, setRiskForecast] = useState([])
  const [tracking, setTracking] = useState(true)
  const [toast, setToast] = useState(null)
  const [sosSent, setSosSent] = useState(null)
  const [sosQueued, setSosQueued] = useState(false)
  const [pendingCount, setPendingCount] = useState(queueLength())
  const [emergencyMessage, setEmergencyMessage] = useState('')
  // Shared across HomeTab (renders the map layer -- destination click +
  // candidate polylines) and PlanTab (renders the control panel): only one
  // tab is mounted at a time, so this state has to live above both, not in
  // either tab, or switching tabs would silently reset a route in progress.
  const [routePickerOpen, setRoutePickerOpen] = useState(false)
  const routePicker = useRoutePicker(tid)
  const posRef = useRef(null)
  const geo = useGeolocation({ enabled: tracking && !SIMULATE_GPS })
  const lastSentGeoTs = useRef(0)

  const showToast = (msg, ms = 4000) => {
    setToast(msg)
    setTimeout(() => setToast(null), ms)
  }

  const load = async () => {
    const [m, s, z, u] = await Promise.all([
      api.get(`/tourists/${tid}`),
      api.get(`/tourists/${tid}/safety-score`),
      api.get('/zones'),
      api.get('/police-units'),
    ])
    setMe(m.data); setScore(s.data); setZones(z.data); setUnits(u.data)
    setTracking(m.data.tracking_enabled)
    posRef.current = [m.data.last_lat, m.data.last_lng]
  }
  useEffect(() => {
    if (tid) load()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once per tid
  }, [tid])

  // Trajectory + dynamic risk forecast. Best-effort refresh alongside the
  // location poll -- neither failing should block the rest of the app.
  useEffect(() => {
    if (!tid) return
    const loadForecasts = () => {
      api.get(`/tourists/${tid}/trajectory-forecast`).then((r) => setTrajectory(r.data.points)).catch(() => {})
      api.get(`/tourists/${tid}/risk-forecast`).then((r) => setRiskForecast(r.data.forecast)).catch(() => {})
    }
    loadForecasts()
    const iv = setInterval(loadForecasts, TRACK_INTERVAL_MS)
    return () => clearInterval(iv)
  }, [tid])

  const pushLocation = async (lat, lng, speedKmh) => {
    posRef.current = [lat, lng]
    const { data } = await api.post(`/tourists/${tid}/location`, { lat, lng, speed_kmh: speedKmh })
    setScore((s) => ({ ...s, score: data.safety_score, band: data.band }))
    setMe((m) => ({ ...m, last_lat: lat, last_lng: lng, safety_score: data.safety_score }))
    if (data.alerts_raised?.length) {
      showToast(`⚠ ${data.alerts_raised.join(', ').replace(/_/g, ' ')}`)
    }
  }

  // Opt-in live tracking. Two sources, chosen by VITE_SIMULATE_GPS:
  //  - simulated: a random walk on a timer, for demos on a machine with no
  //    meaningful GPS (the default, matching the project's existing demo mode)
  //  - real: navigator.geolocation via useGeolocation, pushed whenever the
  //    device reports a new fix (throttled to TRACK_INTERVAL_MS)
  useEffect(() => {
    if (!tracking || !me || !SIMULATE_GPS) return
    const iv = setInterval(() => {
      const [lat, lng] = posRef.current
      const nlat = lat + (Math.random() - 0.5) * 0.002
      const nlng = lng + (Math.random() - 0.5) * 0.002
      pushLocation(nlat, nlng, 5)
    }, TRACK_INTERVAL_MS)
    return () => clearInterval(iv)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- deliberate: only re-arm on tracking/identity change
  }, [tracking, me?.id])

  useEffect(() => {
    if (!tracking || !me || SIMULATE_GPS || !geo.position) return
    const now = Date.now()
    if (now - lastSentGeoTs.current < TRACK_INTERVAL_MS) return
    lastSentGeoTs.current = now
    pushLocation(geo.position.lat, geo.position.lng, geo.position.speedKmh)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geo.position, tracking, me?.id])

  const toggleTracking = async () => {
    const next = !tracking
    setTracking(next)
    await api.post(`/tourists/${tid}/tracking?enabled=${next}`)
  }

  const postSOS = (payload) => api.post(`/tourists/${tid}/sos`, payload)

  // Returns the real dispatch response ({queued: true} when it had to be
  // queued offline) so a caller that needs to report the outcome -- the
  // voice assistant reads it aloud -- can use the actual result rather than
  // waiting on state. Existing button callers ignore the return value.
  const sendSOS = async () => {
    const [lat, lng] = posRef.current
    const message = emergencyMessage.trim() || 'Emergency! Need help.'
    const payload = { lat, lng, message }
    let result = null
    try {
      const { data } = await postSOS(payload)
      setSosSent(data)
      setSosQueued(false)
      result = data
    } catch (err) {
      // No response at all (offline, DNS failure, connection refused) means
      // the request never reached the server -- queue it rather than lose
      // the tap. A real server error (4xx/5xx) DID reach the server, so
      // that's a genuine failure to surface, not something to silently retry.
      if (!err.response) {
        enqueueSOS(payload)
        setPendingCount(queueLength())
        setSosQueued(true)
        result = { queued: true }
      } else {
        throw err
      }
    }
    setEmergencyMessage('')
    load()
    return result
  }

  // Flush any queued SOS the moment connectivity returns, and once on mount
  // in case one was queued in a previous session that never got a chance to
  // retry (the tab was closed, the app was killed, etc).
  useEffect(() => {
    if (!tid) return undefined
    const tryFlush = async () => {
      const sent = await flushQueue((payload) => postSOS(payload))
      if (sent > 0) {
        setPendingCount(queueLength())
        showToast(`✅ ${sent} queued SOS alert${sent > 1 ? 's' : ''} sent`, 5000)
      }
    }
    tryFlush()
    window.addEventListener('online', tryFlush)
    return () => window.removeEventListener('online', tryFlush)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid])

  // Live push of this tourist's own alerts (geofence/anomaly/health/fall),
  // server-side scoped to their own record -- a server-detected event (e.g.
  // from a linked IoT band) shows up immediately instead of waiting for the
  // next poll.
  useWebSocket((ev) => {
    if (ev.event === 'alert') {
      showToast(`⚠ ${ev.type?.replace(/_/g, ' ')}: ${ev.message}`, 5000)
    }
  }, tid ? `/ws/tourist/${tid}` : null)

  const inZones = me ? zones.filter((z) => pointInPoly(me.last_lat, me.last_lng, z.polygon)) : []
  const riskyZone = inZones.find((z) => ['high', 'restricted'].includes(z.risk_level))
  const nearby = me
    ? [...units]
        .map((u) => ({ ...u, dist: haversineKm(me.last_lat, me.last_lng, u.lat, u.lng) }))
        .sort((a, b) => a.dist - b.dist).slice(0, 3)
    : []

  return {
    ready: !!(me && score),
    online, me, score, zones, units, trajectory, riskForecast,
    tracking, toggleTracking, toast,
    sosSent, sosQueued, pendingCount, sendSOS,
    emergencyMessage, setEmergencyMessage,
    posRef, geo, load, pushLocation,
    inZones, riskyZone, nearby,
    routePicker, routePickerOpen, setRoutePickerOpen,
  }
}
