import api from '../api'

// Thin wrapper over the maps/nearby-places backend endpoints -- one place
// components go for "where is X near the tourist", instead of each one
// re-deriving the URL. Mirrors backend/app/services/maps.py + nearby.py:
// every result may carry `demo: true` (maps.py) when no live Maps API key
// is configured; nearby results are always real DB rows regardless.
export function findNearby(touristId, category, radiusM) {
  const params = new URLSearchParams({ category })
  if (radiusM) params.set('radius_m', radiusM)
  return api.get(`/tourists/${touristId}/nearby?${params}`).then((r) => r.data)
}

// On-demand re-geocode for one place name -- used by the itinerary review
// screen's "Locate" button for a destination the automatic upload parse
// couldn't place (e.g. a specific landmark/hotel name, or a typo the
// tourist just fixed). Returns {lat, lng, demo} or {lat: null, lng: null}
// if it still can't be resolved -- never a guessed location.
export function geocodePlace(place) {
  // A finite timeout -- the backend paces its own calls to the free
  // Nominatim service (~1/sec), so a burst of these (auto-locating many
  // destinations at once) is expected to queue up briefly, not hang.
  return api.get('/maps/geocode', { params: { place }, timeout: 10000 }).then((r) => r.data)
}

// Voice-guidance navigation toward the tourist's next confirmed itinerary
// stop (see backend/app/services/navigation.py). Purely data -- whether/how
// to speak it is entirely the caller's (VoiceNavigationAssistant's) choice.
export function getNavigationGuidance(touristId) {
  return api.get(`/tourists/${touristId}/navigation`).then((r) => r.data)
}
