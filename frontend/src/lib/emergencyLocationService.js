import api from '../api'

// Thin wrapper over /incidents/{id}/location + /incidents/{id}/stop-tracking
// (see backend/app/api/emergency.py) -- SOS live location sharing. One
// place both the tourist's tracking loop and the police live map go
// through, instead of each re-deriving these URLs.
export function postEmergencyLocation(incidentId, { lat, lng, accuracyM, speedKmh, headingDeg, demo }) {
  return api.post(
    `/incidents/${incidentId}/location`,
    { lat, lng, accuracy_m: accuracyM ?? null, speed_kmh: speedKmh ?? null, heading_deg: headingDeg ?? null },
    { params: demo ? { demo: true } : undefined },
  ).then((r) => r.data)
}

export function stopEmergencyTracking(incidentId) {
  return api.post(`/incidents/${incidentId}/stop-tracking`).then((r) => r.data)
}

// Police/responder only -- one incident's current position + trail.
export function getEmergencyTrack(incidentId) {
  return api.get(`/incidents/${incidentId}/location`).then((r) => r.data)
}

// Police/responder only -- every incident currently sharing live location,
// for the central dashboard's "LIVE EMERGENCIES" section.
export function listLiveEmergencies() {
  return api.get('/incidents/live').then((r) => r.data)
}
