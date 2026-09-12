import { useEffect, useState } from 'react'
import api from '../api'
import { Card } from './ui.jsx'

// Trip Guardian (Family Live-Share): a tourist can hand a trusted person a
// read-only link -- no account needed on their end. See app/api/guardian.py.
export default function TripGuardianCard({ touristId }) {
  const [guardians, setGuardians] = useState([])
  const [name, setName] = useState('')
  const [contact, setContact] = useState('')
  const [creating, setCreating] = useState(false)
  const [copiedId, setCopiedId] = useState(null)

  const load = () => api.get(`/tourists/${touristId}/guardians`).then((r) => setGuardians(r.data))
  useEffect(() => { load() }, [touristId])

  const create = async (e) => {
    e.preventDefault()
    if (!name.trim()) return
    setCreating(true)
    try {
      await api.post(`/tourists/${touristId}/guardians`, { guardian_name: name, guardian_contact: contact })
      setName('')
      setContact('')
      load()
    } finally {
      setCreating(false)
    }
  }

  const revoke = async (id) => {
    await api.post(`/tourists/${touristId}/guardians/${id}/revoke`)
    load()
  }

  const shareUrl = (token) => `${window.location.origin}/guardian/${token}`

  const copy = async (g) => {
    try {
      await navigator.clipboard.writeText(shareUrl(g.token))
      setCopiedId(g.id)
      setTimeout(() => setCopiedId(null), 2000)
    } catch {
      // Clipboard API can be unavailable (insecure context, permission denied)
      // -- the link is still shown below the button, so nothing is lost.
    }
  }

  const active = guardians.filter((g) => !g.revoked)

  return (
    <Card title="Trip Guardian — Family Live-Share">
      <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">
        Share a read-only link with someone you trust. They can follow your
        trip and are notified immediately if you trigger an SOS — no account needed.
      </p>

      <form onSubmit={create} className="flex flex-col gap-2 mb-3">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Guardian's name (e.g. Mom)"
          className="border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 rounded-lg px-3 py-2 text-sm" />
        <input value={contact} onChange={(e) => setContact(e.target.value)} placeholder="Phone or email (optional)"
          className="border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 rounded-lg px-3 py-2 text-sm" />
        <button disabled={creating || !name.trim()}
          className="bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white text-sm font-semibold py-2 rounded-lg">
          {creating ? 'Creating…' : '+ Create share link'}
        </button>
      </form>

      <div className="space-y-2">
        {active.length === 0 && <div className="text-xs text-slate-400">No active guardians yet.</div>}
        {active.map((g) => (
          <div key={g.id} className="border border-slate-100 dark:border-slate-700 rounded-lg p-2.5 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-medium">{g.guardian_name}</span>
              <button onClick={() => revoke(g.id)} className="text-xs text-red-600 hover:underline">revoke</button>
            </div>
            <div className="flex items-center gap-2 mt-1">
              <input readOnly value={shareUrl(g.token)}
                className="flex-1 text-xs border border-slate-200 dark:border-slate-600 dark:bg-slate-800 rounded px-2 py-1 text-slate-500" />
              <button onClick={() => copy(g)} className="text-xs text-sky-600 font-semibold shrink-0">
                {copiedId === g.id ? 'Copied!' : 'Copy'}
              </button>
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}
