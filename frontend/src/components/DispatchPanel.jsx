import { useEffect, useState } from 'react'
import api from '../api'

// Ranked dispatch candidates for one incident: top pick + backups, with
// distance/ETA. Embedded in the admin Incidents page's expanded incident view.
export default function DispatchPanel({ incidentId }) {
  const [candidates, setCandidates] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setCandidates(null)
    setError('')
    api.get(`/incidents/${incidentId}/dispatch-candidates`)
      .then((r) => { if (!cancelled) setCandidates(r.data) })
      .catch(() => { if (!cancelled) setError('Could not load dispatch candidates.') })
    return () => { cancelled = true }
  }, [incidentId])

  if (error) return <div className="text-sm text-red-600 dark:text-red-400">{error}</div>
  if (!candidates) return <div className="text-sm text-slate-400">Loading candidates…</div>
  if (candidates.length === 0) {
    return <div className="text-sm text-slate-400">No available units nearby.</div>
  }

  return (
    <div className="space-y-1.5">
      {candidates.map((c, i) => (
        <div key={c.unit_id}
          className={`flex items-center justify-between text-sm rounded-lg px-3 py-2 ${
            i === 0
              ? 'bg-sky-50 dark:bg-sky-900/30 border border-sky-200 dark:border-sky-800'
              : 'bg-slate-50 dark:bg-slate-700/40'
          }`}>
          <div className="flex items-center gap-2">
            {i === 0 && <span className="text-xs font-semibold text-sky-700 dark:text-sky-300">TOP PICK</span>}
            <span className="font-medium text-slate-800 dark:text-slate-100">{c.name}</span>
            <span className="text-xs uppercase text-slate-500 dark:text-slate-400">{c.unit_type}</span>
            <span className="text-xs text-slate-400">{c.station}</span>
          </div>
          <div className="text-xs text-slate-600 dark:text-slate-300 whitespace-nowrap">
            {c.distance_km} km · ~{c.eta_min} min
          </div>
        </div>
      ))}
    </div>
  )
}
