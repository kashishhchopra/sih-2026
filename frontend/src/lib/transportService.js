import { findNearby } from './mapsService.js'

// Nearby transport (cabs/autos/buses/metro/rail) is just the "transport"
// category of the same nearby-places lookup used for hospitals/pharmacies
// -- a dedicated module purely so callers reach for `transportService`
// rather than remembering the category string, per the project's service-
// per-domain convention. Deliberately does NOT simulate live booking/seat
// availability -- see backend/app/services/nearby.py's docstring.
export function findNearbyTransport(touristId, radiusM) {
  return findNearby(touristId, 'transport', radiusM)
}
