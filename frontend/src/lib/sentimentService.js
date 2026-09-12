import api from '../api'

// Thin wrapper over sentiment/safety-report endpoints (see
// backend/app/api/safety_reports.py + services/sentiment.py -- real VADER +
// safety-lexicon analysis, optionally enhanced by the configured LLM).
export function previewSentiment(text) {
  return api.post('/sentiment/preview', { text }).then((r) => r.data)
}

export function submitSafetyReport(touristId, text, lat, lng) {
  return api
    .post(`/tourists/${touristId}/safety-reports`, { text, lat: lat ?? null, lng: lng ?? null })
    .then((r) => r.data)
}

export function listSafetyReports(touristId) {
  return api.get(`/tourists/${touristId}/safety-reports`).then((r) => r.data)
}
