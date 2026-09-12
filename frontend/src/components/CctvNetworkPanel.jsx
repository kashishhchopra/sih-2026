import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Card } from './ui.jsx'
import CctvStreamPlayer from './CctvStreamPlayer.jsx'
import { CONNECTION, getCctvNetwork, getCameraStatus, deleteCamera } from '../lib/cctvService'

// The CCTV Network section of the Police Network Dashboard: a surveillance
// console over whatever cameras the backend actually has.
//
// Everything rendered here -- camera names, locations, stream URLs, the
// responsible station, and crucially the LIVE/OFFLINE state -- comes from
// /api/cctv. There is no camera list in this file, and a camera never reads
// LIVE because a row exists: that state is probed backend-side per camera.
//
// The grid adapts to 0, 1, or many cameras; an empty network is a normal
// outcome that gets its own message rather than being padded with anything.

const STATUS_META = {
  [CONNECTION.LIVE]: { label: 'LIVE', dot: 'bg-red-500', badge: 'bg-red-600 text-white', text: 'text-green-400' },
  [CONNECTION.OFFLINE]: { label: 'OFFLINE', dot: 'bg-slate-500', badge: 'bg-slate-700 text-slate-300', text: 'text-slate-500' },
  [CONNECTION.NO_STREAM]: { label: 'NO FEED', dot: 'bg-slate-600', badge: 'bg-slate-700 text-slate-400', text: 'text-slate-500' },
  [CONNECTION.DISABLED]: { label: 'DISABLED', dot: 'bg-slate-600', badge: 'bg-slate-700 text-slate-400', text: 'text-slate-500' },
  [CONNECTION.UNPLAYABLE]: { label: 'NOT VIEWABLE', dot: 'bg-amber-500', badge: 'bg-amber-700 text-amber-100', text: 'text-amber-400' },
  [CONNECTION.UNAVAILABLE]: { label: 'UNAVAILABLE', dot: 'bg-amber-500', badge: 'bg-amber-700 text-amber-100', text: 'text-amber-400' },
  [CONNECTION.UNKNOWN]: { label: 'CONNECTING', dot: 'bg-sky-500', badge: 'bg-sky-800 text-sky-200', text: 'text-sky-400' },
}

function statusMeta(connection) {
  return STATUS_META[connection] || STATUS_META[CONNECTION.UNKNOWN]
}

function camCode(camera) {
  return `CCTV-${String(camera.id).padStart(2, '0')}`
}

function relativeTime(iso) {
  if (!iso) return 'never'
  // The API serialises naive UTC timestamps with no zone suffix, which
  // Date() would otherwise read as local time -- that made a probe from
  // seconds ago render as "6h ago" in +05:30.
  const utc = /[Z+]|-\d{2}:\d{2}$/.test(iso) ? iso : `${iso}Z`
  const seconds = Math.max(0, Math.round((Date.now() - new Date(utc).getTime()) / 1000))
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`
  return `${Math.round(seconds / 3600)}h ago`
}

function CameraCard({ camera, stationName, selected, onSelect, onRetry, retrying }) {
  const meta = statusMeta(camera.connection)
  return (
    <button type="button" onClick={() => onSelect(camera)}
      aria-pressed={selected}
      className={`text-left bg-slate-900 rounded-lg overflow-hidden border transition
        ${selected ? 'border-sky-500 ring-1 ring-sky-500/40' : 'border-slate-700 hover:border-slate-500'}`}>
      <div className="relative h-24">
        <CctvStreamPlayer camera={camera} className="h-24" onRetry={() => onRetry(camera)}
          retrying={retrying} compact />
        <span className={`absolute top-1 left-1 z-10 text-[9px] font-bold px-1.5 py-0.5 rounded flex items-center gap-1 ${meta.badge}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
          {meta.label}
        </span>
        <span className="absolute top-1 right-1 z-10 text-[9px] font-mono text-slate-300 bg-slate-950/70 px-1 rounded">
          {camCode(camera)}
        </span>
      </div>
      <div className="px-2 py-1.5 space-y-0.5">
        <div className="text-[11px] font-semibold text-slate-100 truncate">{camera.label}</div>
        <div className="text-[10px] text-slate-400 truncate">
          📍 {camera.lat.toFixed(4)}, {camera.lng.toFixed(4)}
        </div>
        <div className="text-[10px] text-slate-400 truncate">
          🚓 {stationName || 'Unassigned'}
        </div>
        <div className="flex items-center justify-between text-[9px]">
          <span className="text-slate-500 truncate">{camera.feed_source}</span>
          <span className="text-slate-600">{relativeTime(camera.last_checked_at)}</span>
        </div>
      </div>
    </button>
  )
}

export default function CctvNetworkPanel({
  stations = [], onFocusCamera, selectedCameraId, onCamerasLoaded,
  // Set by the map when a camera marker is clicked -- opens that camera's
  // feed here, which is the other half of the map <-> console selection.
  openCameraId, onOpenHandled,
}) {
  const [cameras, setCameras] = useState([])
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [retryingId, setRetryingId] = useState(null)
  const [expanded, setExpanded] = useState(null)
  const [confirmingDeleteId, setConfirmingDeleteId] = useState(null)
  const [deleting, setDeleting] = useState(false)
  // Scoped to the modal, not the shared network `error` above -- a failed
  // delete must not hide every other working camera behind a false
  // "CCTV Network Unavailable" screen over the whole grid.
  const [deleteError, setDeleteError] = useState('')

  const [q, setQ] = useState('')
  const [stationId, setStationId] = useState('')
  const [connection, setConnection] = useState('')

  const onCamerasLoadedRef = useRef(onCamerasLoaded)
  onCamerasLoadedRef.current = onCamerasLoaded

  const load = useCallback(async ({ quiet = false } = {}) => {
    if (!quiet) setLoading(true)
    try {
      const data = await getCctvNetwork({
        q: q || undefined,
        stationId: stationId === '' ? undefined : Number(stationId),
        connection: connection || undefined,
      })
      setCameras(data.cameras)
      setSummary(data.summary)
      setError(null)
      // Hand the map the same records, so its markers are generated from
      // the API's coordinates rather than a second, divergent source.
      onCamerasLoadedRef.current?.(data.cameras)
    } catch {
      // A CCTV outage must not take the rest of the dashboard with it --
      // this section reports its own failure and the page keeps working.
      setError('Unable to retrieve camera feeds.')
    } finally {
      setLoading(false)
    }
  }, [q, stationId, connection])

  useEffect(() => { load() }, [load])

  // Re-poll on the interval the backend advertises, so status changes show
  // up without a page refresh. Polling matches how the rest of this app
  // refreshes (VITE_POLL_INTERVAL_MS) rather than adding a second real-time
  // transport alongside the existing WebSocket.
  useEffect(() => {
    const seconds = summary?.refresh_interval_seconds
    if (!seconds) return undefined
    const timer = setInterval(() => load({ quiet: true }), seconds * 1000)
    return () => clearInterval(timer)
  }, [summary?.refresh_interval_seconds, load])

  // A marker click asks for a camera by id; open it once its record is
  // loaded, then clear the request so re-renders don't reopen it.
  useEffect(() => {
    if (openCameraId == null) return
    const cam = cameras.find((c) => c.id === openCameraId)
    if (!cam) return
    setExpanded(cam)
    onOpenHandled?.()
  }, [openCameraId, cameras, onOpenHandled])

  const stationName = useMemo(() => {
    const byId = Object.fromEntries(stations.map((s) => [s.id, s.name]))
    return (id) => (id == null ? null : byId[id] || `Station ${id}`)
  }, [stations])

  const retry = async (camera) => {
    setRetryingId(camera.id)
    try {
      const status = await getCameraStatus(camera.id, { force: true })
      setCameras((list) => list.map((c) => (
        c.id === camera.id
          ? { ...c, connection: status.connection, last_checked_at: status.last_checked_at }
          : c
      )))
      setExpanded((cur) => (cur && cur.id === camera.id
        ? { ...cur, connection: status.connection, last_checked_at: status.last_checked_at }
        : cur))
    } catch {
      setError('Unable to reach the CCTV service.')
    } finally {
      setRetryingId(null)
    }
  }

  const remove = async (camera) => {
    if (confirmingDeleteId !== camera.id) {
      setConfirmingDeleteId(camera.id)
      return
    }
    setDeleting(true)
    setDeleteError('')
    try {
      await deleteCamera(camera.id)
      setCameras((list) => list.filter((c) => c.id !== camera.id))
      setExpanded(null)
      setConfirmingDeleteId(null)
    } catch {
      setDeleteError('Unable to remove this camera.')
    } finally {
      setDeleting(false)
    }
  }

  const select = (camera) => {
    setConfirmingDeleteId(null)
    setDeleteError('')
    setExpanded(camera)
    onFocusCamera?.(camera)
  }

  const headerCounts = summary && (
    <div className="flex items-center gap-3 text-[11px]">
      <span className="text-slate-400">{summary.total} cameras</span>
      <span className="text-green-400">● {summary.live} live</span>
      <span className="text-slate-500">○ {summary.offline} offline</span>
    </div>
  )

  return (
    <Card title="CCTV Network" actions={headerCounts}>
      {/* ---- filters (applied server-side) ---- */}
      <div className="flex flex-wrap gap-2 mb-3">
        <input value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="Search cameras…" aria-label="Search cameras"
          className="flex-1 min-w-[140px] bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-100 placeholder-slate-500" />
        <select value={stationId} onChange={(e) => setStationId(e.target.value)}
          aria-label="Filter by police station"
          className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-slate-100">
          <option value="">All stations</option>
          {stations.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <select value={connection} onChange={(e) => setConnection(e.target.value)}
          aria-label="Filter by status"
          className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-slate-100">
          <option value="">Any status</option>
          <option value={CONNECTION.LIVE}>Live</option>
          <option value={CONNECTION.OFFLINE}>Offline</option>
          <option value={CONNECTION.NO_STREAM}>No feed</option>
          <option value={CONNECTION.DISABLED}>Disabled</option>
        </select>
      </div>

      {loading && <div className="text-sm text-slate-400 py-6 text-center">Loading CCTV Network…</div>}

      {!loading && error && (
        <div className="py-6 text-center">
          <div className="text-sm font-semibold text-red-400">CCTV Network Unavailable</div>
          <div className="text-xs text-slate-400 mt-1">{error}</div>
          <button type="button" onClick={() => load()}
            className="mt-3 text-xs font-semibold px-3 py-1.5 rounded bg-slate-700 hover:bg-slate-600 text-slate-100">
            Retry
          </button>
        </div>
      )}

      {!loading && !error && cameras.length === 0 && (
        <div className="py-6 text-center">
          <div className="text-sm text-slate-300">No live CCTV sources currently available.</div>
          <div className="text-xs text-slate-500 mt-1">
            {q || stationId || connection
              ? 'No cameras match these filters.'
              : summary?.provider_configured
                ? 'The configured provider returned no cameras.'
                : 'Register a camera with its stream URL, or configure a CCTV provider, to populate this console.'}
          </div>
        </div>
      )}

      {!loading && !error && cameras.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
          {cameras.map((c) => (
            <CameraCard key={c.id} camera={c} stationName={stationName(c.assigned_station_id)}
              selected={selectedCameraId === c.id} onSelect={select}
              onRetry={retry} retrying={retryingId === c.id} />
          ))}
        </div>
      )}

      {/* ---- expanded single-camera view ---- */}
      {expanded && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-[2000] p-4"
          role="dialog" aria-label={`Camera ${expanded.label}`}
          onClick={() => setExpanded(null)}>
          <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-2xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}>
            <div className="relative">
              <CctvStreamPlayer camera={expanded} className="h-72"
                onRetry={() => retry(expanded)} retrying={retryingId === expanded.id} />
              <span className={`absolute top-2 left-2 z-10 text-[10px] font-bold px-2 py-0.5 rounded flex items-center gap-1 ${statusMeta(expanded.connection).badge}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${statusMeta(expanded.connection).dot}`} />
                {statusMeta(expanded.connection).label}
              </span>
              <span className="absolute top-2 right-2 z-10 text-[10px] font-mono text-slate-300 bg-slate-950/70 px-1.5 py-0.5 rounded">
                {camCode(expanded)}
              </span>
            </div>
            <div className="p-4 text-sm space-y-2">
              <div className="font-bold text-slate-100">{expanded.label}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-800/60 rounded-lg px-3 py-2">
                  <div className="text-slate-500 text-[10px]">Location</div>
                  <div className="text-slate-200">{expanded.lat.toFixed(4)}, {expanded.lng.toFixed(4)}</div>
                </div>
                <div className="bg-slate-800/60 rounded-lg px-3 py-2">
                  <div className="text-slate-500 text-[10px]">Police Station</div>
                  <div className="text-slate-200">{stationName(expanded.assigned_station_id) || 'Unassigned'}</div>
                </div>
                <div className="bg-slate-800/60 rounded-lg px-3 py-2">
                  <div className="text-slate-500 text-[10px]">Stream</div>
                  <div className="text-slate-200 uppercase">{expanded.stream_type}</div>
                </div>
                <div className="bg-slate-800/60 rounded-lg px-3 py-2">
                  <div className="text-slate-500 text-[10px]">Last checked</div>
                  <div className="text-slate-200">{relativeTime(expanded.last_checked_at)}</div>
                </div>
              </div>
              {/* Attribution travels with the feed, as the source requires. */}
              <div className="text-[11px] text-slate-500">
                Source: {expanded.feed_source}
                {expanded.attribution && <> · {expanded.attribution}</>}
                {expanded.source_url && (
                  <> · <a href={expanded.source_url} target="_blank" rel="noreferrer noopener"
                    className="text-sky-400 hover:underline">source</a></>
                )}
              </div>
              <div className="flex gap-2 pt-1">
                <button type="button" onClick={() => { onFocusCamera?.(expanded); setExpanded(null) }}
                  className="flex-1 bg-sky-700 hover:bg-sky-600 text-slate-100 text-xs font-semibold py-2 rounded-lg">
                  Show on map
                </button>
                <button type="button" onClick={() => setExpanded(null)}
                  className="flex-1 bg-slate-700 hover:bg-slate-600 text-slate-100 text-xs font-semibold py-2 rounded-lg">
                  Close
                </button>
              </div>
              {/* Requires a second tap, same confirm-again pattern used
                  elsewhere in this app for other hard-to-undo actions
                  (e.g. regenerating a Digital ID's QR code). Admin-only
                  server-side (DELETE /cctv/{id}); a non-admin sees the
                  real 403 surfaced as the panel's own error state. */}
              <button type="button" onClick={() => remove(expanded)} disabled={deleting}
                className={`w-full text-xs font-semibold py-2 rounded-lg border transition disabled:opacity-60 ${
                  confirmingDeleteId === expanded.id
                    ? 'bg-red-600 hover:bg-red-700 text-white border-red-600'
                    : 'bg-transparent hover:bg-red-950/40 text-red-400 border-red-900/60'}`}>
                {deleting ? 'Removing…'
                  : confirmingDeleteId === expanded.id ? 'Tap again to confirm removal'
                  : 'Remove camera'}
              </button>
              {deleteError && <div className="text-[11px] text-red-400 text-center">{deleteError}</div>}
            </div>
          </div>
        </div>
      )}
    </Card>
  )
}
