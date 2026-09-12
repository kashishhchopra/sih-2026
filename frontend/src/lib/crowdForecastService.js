import api from '../api'

// Thin wrapper over /crowd/* (see backend/app/api/crowd_forecast.py).
export function getCrowdForecast() {
  return api.get('/crowd/forecast').then((r) => r.data)
}

export function getPoiQueueEstimate(poiId) {
  return api.get(`/crowd/forecast/poi/${poiId}`).then((r) => r.data)
}
