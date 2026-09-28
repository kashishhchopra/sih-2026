// Centralised, env-driven frontend configuration (no hardcoded hosts/coords).
// Values come from Vite env (VITE_*) with sensible fallbacks; the map default
// can also be overridden at runtime by the backend's /api/config endpoint.

export const API_BASE = import.meta.env.VITE_API_BASE || '/api'
export const WS_PATH = import.meta.env.VITE_WS_PATH || '/ws/alerts'
export const SHOW_DEMO_LOGINS = (import.meta.env.VITE_SHOW_DEMO ?? 'true') !== 'false'
// Demo-login shortcuts are deploy-config, not source: VITE_DEMO_LOGINS is a
// JSON array of {label,email,password}. Empty by default -- a real deployment
// gets no working credentials baked into the bundle even if SHOW_DEMO_LOGINS
// is left on by accident. Format: '[{"label":"Admin","email":"a@b.com","password":"x"}]'
export const DEMO_LOGINS = (() => {
  const raw = import.meta.env.VITE_DEMO_LOGINS
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
})()
export const POLL_INTERVAL_MS = Number(import.meta.env.VITE_POLL_INTERVAL_MS || 8000)
export const TRACK_INTERVAL_MS = Number(import.meta.env.VITE_TRACK_INTERVAL_MS || 5000)
// Demo/dev convenience: simulate a random walk instead of real GPS, since a
// laptop/desktop rarely has meaningful geolocation and a live demo needs
// motion on the map without physically moving. Default true; a real device
// build sets VITE_SIMULATE_GPS=false to use navigator.geolocation instead.
export const SIMULATE_GPS = (import.meta.env.VITE_SIMULATE_GPS ?? 'true') !== 'false'

export const DEFAULT_MAP = {
  center: [
    Number(import.meta.env.VITE_MAP_CENTER_LAT || 26.1445),
    Number(import.meta.env.VITE_MAP_CENTER_LNG || 91.7362),
  ],
  zoom: Number(import.meta.env.VITE_MAP_ZOOM || 13),
}

let _cachedMap = null

// Fetch map defaults from the backend once; fall back to env defaults on error.
export async function loadMapConfig(apiGet) {
  if (_cachedMap) return _cachedMap
  try {
    const { data } = await apiGet('/config')
    _cachedMap = { center: data.map.center, zoom: data.map.zoom }
  } catch {
    _cachedMap = DEFAULT_MAP
  }
  return _cachedMap
}
