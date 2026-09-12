import api from '../api'

// Thin wrapper over GET /tourists/{id}/trip-plan (see backend/app/api/trip_planner.py).
export function getTripPlan(touristId, days) {
  return api
    .get(`/tourists/${touristId}/trip-plan`, { params: days ? { days } : {} })
    .then((r) => r.data)
}
