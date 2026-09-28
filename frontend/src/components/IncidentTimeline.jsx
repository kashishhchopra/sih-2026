import { useEffect, useState } from 'react'
import api from '../api'
import TrailReplay from './TrailReplay.jsx'

const KIND_ICON = { status: '●', anomaly: '⚠', alert: '🔔' }
const KIND_CLS = {
  status: 'text-sky-600',
  anomaly: 'text-orange-600',
  alert: 'text-red-600',
}

// Reconstructs an incident minute-by-minute (status changes, the anomalous
// pings and alerts that led up to it) and, if the incident has a tourist,
// lets the operator replay their trail on the map -- see
// GET /incidents/{id}/timeline and TrailReplay.jsx.
export default function IncidentTimeline({ incidentId, touristId }) {
  const [timeline, setTimeline] = useState(null)
  const [pings, setPings] = useState(null)

  useEffect(() => {
    api.get(`/incidents/${incidentId}/timeline`).then((r) => setTimeline(r.data))
    if (touristId) {
      api.get(`/tourists/${touristId}/pings?limit=200`).then((r) => setPings(r.data))
    }
  }, [incidentId, touristId])

  if (!timeline) return <div className="text-sm text-slate-400">Loading timeline…</div>

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        {timeline.events.length === 0 && (
          <div className="text-sm text-slate-400">No timeline events recorded yet.</div>
        )}
        {timeline.events.map((e, i) => (
          <div key={i} className="flex items-start gap-2 text-xs">
            <span className={`mt-0.5 ${KIND_CLS[e.kind] || 'text-slate-500'}`}>{KIND_ICON[e.kind] || '•'}</span>
            <span className="text-slate-400 w-20 shrink-0">{new Date(e.timestamp).toLocaleTimeString()}</span>
            <span className="font-semibold capitalize">{e.label}</span>
            {e.detail && <span className="text-slate-500">— {e.detail}</span>}
          </div>
        ))}
      </div>

      {pings && pings.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-slate-500 mb-2 uppercase tracking-wide">Replay</div>
          <TrailReplay pings={pings} />
        </div>
      )}
    </div>
  )
}
