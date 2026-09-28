import L from 'leaflet'

// Inline SVG divIcons so we don't depend on external marker image assets (CSP-safe).
export function pin(color, glyph = '', pulse = false) {
  return L.divIcon({
    className: '',
    html: `<div style="position:relative;width:26px;height:26px">
      <div class="${pulse ? 'sos-pulse' : ''}" style="width:20px;height:20px;background:${color};border:2px solid #fff;border-radius:50% 50% 50% 0;
        transform:rotate(-45deg);box-shadow:0 1px 4px rgba(0,0,0,.4);position:absolute;left:3px;top:2px"></div>
      <div style="position:absolute;left:0;top:2px;width:26px;text-align:center;font-size:11px;line-height:20px">${glyph}</div>
    </div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 24],
    popupAnchor: [0, -22],
  })
}

export const touristIcon = (score) => {
  const color = score >= 75 ? '#16a34a' : score >= 50 ? '#eab308' : score >= 25 ? '#f97316' : '#dc2626'
  return pin(color)
}
export const sosIcon = pin('#dc2626', '🚨', true)
export const missingIcon = pin('#7c3aed', '?')
export const policeIcon = pin('#2563eb', '🚔')

// Area-based police network map: station status colour, CCTV markers, and
// the virtual "Central Safety Dashboard" hub node -- see pages/admin/PoliceNetwork.jsx.
export const stationIcon = (status) => {
  const color = status === 'critical' ? '#dc2626' : status === 'caution' ? '#eab308' : '#16a34a'
  return pin(color, '🚓', status === 'critical')
}
export const cameraIcon = pin('#f97316', '📹')
export const centralIcon = pin('#7c3aed', '🛰️')

export const riskColor = {
  low: '#22c55e',
  medium: '#eab308',
  high: '#f97316',
  restricted: '#dc2626',
}
