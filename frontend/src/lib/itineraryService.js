import api from '../api'

// Thin wrapper over /tourists/{id}/itinerary-documents (see
// backend/app/api/itinerary.py). Upload always resolves (201) even when
// extraction fails -- the response's `status`/`error` fields say why,
// they never come back as a rejected promise for a "just couldn't read it"
// case, only for real request failures (auth, network, validation).
export function uploadItineraryDocument(touristId, file) {
  const form = new FormData()
  form.append('file', file)
  return api.post(`/tourists/${touristId}/itinerary-documents`, form, {
    // Content-Type is left for axios/the browser to set (it fills in the
    // multipart boundary automatically for a FormData body -- setting it
    // manually here would omit that boundary and break parsing).
    // A generous but finite timeout: OCR on a large photo can genuinely
    // take a while, but the tourist should get a clear error rather than
    // an unexplained spinner if something really is stuck.
    timeout: 45000,
  }).then((r) => r.data)
}

export function listItineraryDocuments(touristId) {
  return api.get(`/tourists/${touristId}/itinerary-documents`).then((r) => r.data)
}

export function updateItineraryDocument(touristId, docId, extracted) {
  return api.patch(`/tourists/${touristId}/itinerary-documents/${docId}`, extracted).then((r) => r.data)
}

export function confirmItineraryDocument(touristId, docId) {
  return api.post(`/tourists/${touristId}/itinerary-documents/${docId}/confirm`).then((r) => r.data)
}
