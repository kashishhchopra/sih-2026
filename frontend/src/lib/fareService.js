import api from '../api'

// Thin wrapper over /fare/* and /tourists/{id}/fare-checks (see
// backend/app/api/fare.py + services/fare.py). Every estimate is computed
// from real route distance/duration (services/maps.py) x a configurable
// rate card -- never a single hardcoded price.
export function listTransportTypes() {
  return api.get('/fare/transport-types').then((r) => r.data)
}

export function createFareCheck(touristId, payload) {
  return api.post(`/tourists/${touristId}/fare-checks`, payload).then((r) => r.data)
}

export function listFareChecks(touristId) {
  return api.get(`/tourists/${touristId}/fare-checks`).then((r) => r.data)
}

export function reportFare(touristId, checkId, note) {
  return api
    .post(`/tourists/${touristId}/fare-checks/${checkId}/report`, { note: note || '' })
    .then((r) => r.data)
}
