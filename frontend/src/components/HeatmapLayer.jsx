import { useEffect } from 'react'
import { useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet.heat'

// leaflet.heat is a plain Leaflet plugin (attaches L.heatLayer to the global
// Leaflet namespace), not a react-leaflet component, so it's added/removed
// imperatively via useMap rather than rendered as JSX.
//
// `points` is [[lat, lng, intensity], ...]. Replaces the previous approach of
// drawing a fixed-radius Circle per high-risk zone, which only ever showed
// zone shapes, not where incidents actually happened.
export default function HeatmapLayer({ points, radius = 28, blur = 22 }) {
  const map = useMap()

  useEffect(() => {
    if (!points || points.length === 0) return undefined
    const layer = L.heatLayer(points, { radius, blur, maxZoom: 16 }).addTo(map)
    return () => {
      map.removeLayer(layer)
    }
  }, [map, points, radius, blur])

  return null
}
