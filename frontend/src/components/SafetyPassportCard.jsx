import { useState } from 'react'
import api from '../api'
import { Card } from './ui.jsx'

// Digital Safety Passport + QR: a collapsible card so the default view stays
// uncluttered (same pattern as the safe-route planner toggle in TouristApp).
// Fetches on first open rather than on mount -- a responder scanning a QR
// hits the endpoint directly, this is the tourist's own on-demand view.
export default function SafetyPassportCard({ touristId }) {
  const [open, setOpen] = useState(false)
  const [passport, setPassport] = useState(null)
  const [loading, setLoading] = useState(false)

  const toggle = async () => {
    const next = !open
    setOpen(next)
    if (next && !passport) {
      setLoading(true)
      try {
        const { data } = await api.get(`/tourists/${touristId}/passport`)
        setPassport(data)
      } finally {
        setLoading(false)
      }
    }
  }

  return (
    <div>
      <button onClick={toggle}
        className="w-full text-sm font-semibold text-sky-700 dark:text-sky-400 bg-sky-50 dark:bg-sky-900/30 rounded-xl py-2">
        {open ? 'Hide safety passport ▲' : '🪪 Digital Safety Passport'}
      </button>

      {open && (
        <div className="mt-3">
          {loading && <div className="text-sm text-slate-400 text-center py-4">Loading…</div>}
          {passport && (
            <Card title="Tourist Safety Passport">
              <div className="flex gap-4 items-start">
                <img src={passport.qr_png_base64} alt="Digital ID QR code"
                  className="w-24 h-24 border border-slate-200 dark:border-slate-600 rounded-lg shrink-0" />
                <div className="text-sm space-y-1">
                  <div><span className="text-slate-400">Digital ID:</span> <span className="font-mono">{passport.digital_id}</span></div>
                  <div><span className="text-slate-400">Language:</span> {passport.preferred_language}</div>
                  <div><span className="text-slate-400">Current risk:</span> {Math.round(passport.safety_score)}</div>
                  <div><span className="text-slate-400">Status:</span> <span className="capitalize">{passport.current_status}</span></div>
                  {passport.device ? (
                    <div><span className="text-slate-400">Device:</span> Smart Band ({Math.round(passport.device.battery_pct ?? 0)}%{passport.device.is_online ? ', online' : ', offline'})</div>
                  ) : (
                    <div><span className="text-slate-400">Device:</span> none linked</div>
                  )}
                </div>
              </div>
              <div className="mt-3 pt-3 border-t border-slate-100 dark:border-slate-700 text-xs text-slate-500 dark:text-slate-400">
                <div className="font-semibold text-slate-600 dark:text-slate-300 mb-1">Emergency contacts</div>
                {passport.emergency_contacts.map((c, i) => (
                  <div key={i}>{c.name} ({c.relation}) — {c.phone}</div>
                ))}
                {passport.emergency_contacts.length === 0 && <div>None on file.</div>}
              </div>
              <div className="mt-3 text-[11px] text-slate-400">
                A responder scanning this QR code sees exactly this information —
                nothing more.
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
