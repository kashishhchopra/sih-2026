import api from '../api'

// Thin wrapper over /cctv (see backend/app/api/cctv.py) -- the CCTV network
// on the Police Network Dashboard.
//
// Deliberately the ONLY place the frontend knows a camera URL exists at
// all: every stream URL, camera name, location and status arrives from the
// backend, so there is no camera list to hardcode here. Filtering is passed
// through as query params rather than done in the browser, so a force with
// hundreds of cameras doesn't ship its whole directory to every dashboard.

export function getCctvNetwork({ q, stationId, zoneId, connection } = {}) {
  const params = {}
  if (q) params.q = q
  if (stationId != null) params.station_id = stationId
  if (zoneId != null) params.zone_id = zoneId
  if (connection) params.connection = connection
  return api.get('/cctv', { params }).then((r) => r.data)
}

export function getCamera(cameraId) {
  return api.get(`/cctv/${cameraId}`).then((r) => r.data)
}

/** Re-check one camera. `force` skips the backend's status cache -- what the
 * Retry button on an offline feed calls. */
export function getCameraStatus(cameraId, { force = false } = {}) {
  return api.get(`/cctv/${cameraId}/status`, { params: force ? { force: true } : undefined })
    .then((r) => r.data)
}

/** Admin-only: re-import camera metadata from the configured provider. */
export function refreshCctvProvider() {
  return api.post('/cctv/refresh').then((r) => r.data)
}

/** Admin-only: remove a camera that will never carry a usable feed. */
export function deleteCamera(cameraId) {
  return api.delete(`/cctv/${cameraId}`).then((r) => r.data)
}

// Connection states the backend reports (services/cctv.py). Kept here so the
// UI has one vocabulary rather than scattering string literals.
export const CONNECTION = {
  LIVE: 'live',
  OFFLINE: 'offline',
  NO_STREAM: 'no_stream',
  DISABLED: 'disabled',
  UNPLAYABLE: 'unplayable',
  // Source answered, but is serving a "camera unavailable" notice image
  // rather than a view -- reachable, yet not a live picture.
  UNAVAILABLE: 'unavailable',
  UNKNOWN: 'unknown',
}
