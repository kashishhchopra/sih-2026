import api from '../api'

// Thin wrapper over /festivals/* (see backend/app/api/festivals.py).
export function listFestivals(params) {
  return api.get('/festivals', { params }).then((r) => r.data)
}

export function festivalsNear(lat, lng, radiusKm, withinDays) {
  return api
    .get('/festivals/near', { params: { lat, lng, radius_km: radiusKm, within_days: withinDays } })
    .then((r) => r.data)
}
