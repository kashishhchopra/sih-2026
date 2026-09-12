// Haversine distance in kilometres between two [lat,lng] points.
export function haversineKm(lat1, lng1, lat2, lng2) {
  const R = 6371
  const dLat = ((lat2 - lat1) * Math.PI) / 180
  const dLng = ((lng2 - lng1) * Math.PI) / 180
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

// Point-in-polygon (ray casting) for rings given as [[lat,lng], ...].
//
// Mirrors the backend's Shapely check in app/services/geo.py so the tourist view
// can render a geofence warning immediately, without waiting for the server to
// answer. The backend remains the authority: this is presentation only, and the
// two must agree, which is what the tests here pin down.
export function pointInPoly(lat, lng, poly) {
  if (!poly || poly.length < 3) return false
  let inside = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [yi, xi] = poly[i]
    const [yj, xj] = poly[j]
    const intersect =
      (xi > lng) !== (xj > lng) && lat < ((yj - yi) * (lng - xi)) / (xj - xi) + yi
    if (intersect) inside = !inside
  }
  return inside
}
