import { useEffect, useState } from 'react'
import api from '../api'
import { Card } from './ui.jsx'

// Privacy & Consent Dashboard: what a tourist can see and control about
// their own tracking data. See services/privacy.py.
export default function PrivacyCard({ touristId }) {
  const [report, setReport] = useState(null)
  const [retentionDays, setRetentionDays] = useState(90)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleted, setDeleted] = useState(null)

  const load = () => api.get(`/tourists/${touristId}/privacy`).then((r) => {
    setReport(r.data)
    setRetentionDays(r.data.data_retention_days)
  })
  useEffect(() => { load() }, [touristId])

  const saveRetention = async () => {
    setSaving(true)
    try {
      await api.patch(`/tourists/${touristId}/privacy`, { data_retention_days: Number(retentionDays) })
      load()
    } finally {
      setSaving(false)
    }
  }

  const deleteHistory = async () => {
    if (!confirm('Delete all stored GPS location history now? This cannot be undone.')) return
    setDeleting(true)
    try {
      const { data } = await api.delete(`/tourists/${touristId}/location-history`)
      setDeleted(data.pings_deleted)
      load()
    } finally {
      setDeleting(false)
    }
  }

  if (!report) return null

  return (
    <Card title="Privacy &amp; Consent">
      <div className="space-y-3 text-sm">
        <div className="flex items-center justify-between">
          <span className="text-slate-500 dark:text-slate-400">Location pings stored</span>
          <span className="font-semibold">{report.location_pings_stored}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-slate-500 dark:text-slate-400">Auto-deleted after trip ends</span>
          <span className="font-semibold">{new Date(report.auto_purge_at).toLocaleDateString()}</span>
        </div>

        <div>
          <label className="text-xs text-slate-500 dark:text-slate-400">Keep location history for (days after trip ends)</label>
          <div className="flex items-center gap-2 mt-1">
            <input type="number" min={1} max={365} value={retentionDays}
              onChange={(e) => setRetentionDays(e.target.value)}
              className="w-24 border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 rounded-lg px-2 py-1.5 text-sm" />
            <button onClick={saveRetention} disabled={saving}
              className="text-xs font-semibold text-sky-600 disabled:opacity-50">
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>

        <button onClick={deleteHistory} disabled={deleting}
          className="w-full text-sm font-semibold text-red-600 border border-red-200 dark:border-red-900/50 rounded-lg py-2 disabled:opacity-50">
          {deleting ? 'Deleting…' : '🗑 Delete my location history now'}
        </button>
        {deleted != null && (
          <div className="text-xs text-green-600 text-center">{deleted} location record(s) deleted.</div>
        )}

        <div className="text-[11px] text-slate-400 pt-1">
          Your location history is used only for safety scoring and is never
          shared beyond this platform. You control how long it's kept, and can
          delete it at any time.
        </div>
      </div>
    </Card>
  )
}
