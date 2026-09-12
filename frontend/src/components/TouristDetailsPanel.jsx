import { useEffect, useState } from 'react'
import api from '../api'

// The tourist behind one incident -- their registration photo, digital
// hash ID, and other identity/contact detail -- so an operator opening a
// case's "Details" doesn't have to separately search the tourist list to
// see who this actually is. Embedded in the admin Incidents page's
// expanded incident view (see DispatchPanel.jsx for the sibling tab).
export default function TouristDetailsPanel({ touristId }) {
  const [tourist, setTourist] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!touristId) return undefined
    let cancelled = false
    setTourist(null)
    setError('')
    api.get(`/tourists/${touristId}`)
      .then((r) => { if (!cancelled) setTourist(r.data) })
      .catch(() => { if (!cancelled) setError('Could not load tourist details.') })
    return () => { cancelled = true }
  }, [touristId])

  if (!touristId) return <div className="text-sm text-slate-400">This incident has no linked tourist.</div>
  if (error) return <div className="text-sm text-red-600 dark:text-red-400">{error}</div>
  if (!tourist) return <div className="text-sm text-slate-400">Loading tourist details…</div>

  return (
    <div className="flex flex-col sm:flex-row gap-4">
      {tourist.photo && (
        <img src={tourist.photo} alt={tourist.full_name}
          className="w-24 h-24 rounded-xl object-cover border border-slate-200 dark:border-slate-600 shrink-0" />
      )}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm flex-1">
        <div className="col-span-2">
          <div className="font-bold text-slate-800 dark:text-slate-100">{tourist.full_name}</div>
          <div className="text-xs font-mono text-sky-600 dark:text-sky-400">{tourist.digital_id}</div>
        </div>
        <div><span className="text-slate-400">Phone:</span> {tourist.phone}</div>
        <div><span className="text-slate-400">Nationality:</span> {tourist.nationality}</div>
        <div><span className="text-slate-400">Document:</span> {tourist.document_type} · {tourist.document_number}</div>
        <div><span className="text-slate-400">Hotel:</span> {tourist.hotel || '—'}</div>
        <div><span className="text-slate-400">Safety score:</span> {Math.round(tourist.safety_score)}</div>
        <div><span className="text-slate-400">Status:</span> {tourist.status}</div>
        {tourist.emergency_contacts?.length > 0 && (
          <div className="col-span-2 mt-1">
            <div className="text-xs text-slate-400 mb-1">Emergency Contacts</div>
            <div className="flex flex-wrap gap-1.5">
              {tourist.emergency_contacts.map((c, i) => (
                <span key={i} className="text-xs bg-slate-100 dark:bg-slate-700 px-2 py-1 rounded-full">
                  {c.name} ({c.relation}) · {c.phone}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
