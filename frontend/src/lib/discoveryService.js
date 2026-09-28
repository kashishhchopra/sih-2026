import api from '../api'

// Thin wrapper over /discovery/* (see backend/app/api/discovery.py). Every
// GET here is already offline-capable for free: the PWA's Workbox
// NetworkFirst cache (frontend/vite.config.js's `api-get-cache` rule)
// transparently serves the last good response when there's no network --
// same mechanism SafetyCardPanel/OfflineTripCard rely on, so there's no
// separate localStorage cache to keep in sync here.
export function getDiscovery(lat, lng, radiusKm, categories) {
  return api
    .get('/discovery', {
      params: { lat, lng, radius_km: radiusKm, ...(categories ? { categories: categories.join(',') } : {}) },
    })
    .then((r) => r.data)
}

export function getOfflineBundle(lat, lng, radiusKm) {
  return api
    .get('/discovery/offline-bundle', { params: { lat, lng, radius_km: radiusKm } })
    .then((r) => r.data)
}
