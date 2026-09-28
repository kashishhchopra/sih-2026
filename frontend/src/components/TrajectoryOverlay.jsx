import { Polyline, CircleMarker, Popup } from 'react-leaflet'

// Renders a predicted future path as a dashed line, with a small ring marker
// at the final predicted point. `points` is [{lat, lng, eta_min}, ...],
// oldest (soonest ETA) first -- the shape returned by
// GET /tourists/{id}/trajectory-forecast.
export default function TrajectoryOverlay({ points, color = '#0284c7' }) {
  if (!points || points.length === 0) return null

  const path = points.map((p) => [p.lat, p.lng])
  const last = points[points.length - 1]

  return (
    <>
      <Polyline positions={path} pathOptions={{ color, weight: 2.5, dashArray: '6 6', opacity: 0.8 }} />
      <CircleMarker
        center={[last.lat, last.lng]}
        radius={6}
        pathOptions={{ color, fillColor: color, fillOpacity: 0.6, weight: 2 }}
      >
        <Popup>Predicted position in ~{Math.round(last.eta_min)} min</Popup>
      </CircleMarker>
    </>
  )
}
