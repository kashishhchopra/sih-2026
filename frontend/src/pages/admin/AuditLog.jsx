import { useEffect, useState } from 'react'
import api from '../../api'
import { Card } from '../../components/ui.jsx'

const HAZARD_ICON = { flood: '🌊', landslide: '⛰️', earthquake: '🌍', storm: '⛈️' }

function AnchorPanel() {
  const [anchors, setAnchors] = useState([])
  const [publishing, setPublishing] = useState(false)
  const [verifying, setVerifying] = useState(null)
  const [results, setResults] = useState({})

  const load = () => api.get('/anchors').then((r) => setAnchors(r.data))
  useEffect(() => { load() }, [])

  const publish = async () => {
    setPublishing(true)
    try {
      await api.post('/anchors')
      load()
    } finally {
      setPublishing(false)
    }
  }

  const verify = async (id) => {
    setVerifying(id)
    try {
      const { data } = await api.get(`/anchors/${id}/verify`)
      setResults((r) => ({ ...r, [id]: data }))
    } finally {
      setVerifying(null)
    }
  }

  return (
    <Card title="External Hash-Chain Anchoring" actions={
      <button onClick={publish} disabled={publishing}
        className="text-xs font-semibold text-sky-600 disabled:opacity-50">
        {publishing ? 'Publishing…' : '+ Anchor now'}
      </button>
    }>
      <p className="text-xs text-slate-500 mb-3">
        Every root fingerprint below is a tamper-evident snapshot of every tourist's ID
        chain, published to an append-only ledger outside this database. Anyone can verify
        a record existed unchanged at that time.
      </p>
      <div className="space-y-2">
        {anchors.length === 0 && <div className="text-sm text-slate-400">No anchors published yet.</div>}
        {anchors.map((a) => {
          const result = results[a.id]
          return (
            <div key={a.id} className="border border-slate-100 rounded-lg p-2.5 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-mono text-slate-600">{a.root_hash.slice(0, 24)}…</span>
                <span className="text-slate-400">{new Date(a.created_at).toLocaleString()}</span>
              </div>
              <div className="flex items-center justify-between mt-1">
                <span className="text-slate-500">{a.tourist_count} tourists · {a.block_count} blocks · target: {a.anchor_target}</span>
                <button onClick={() => verify(a.id)} disabled={verifying === a.id}
                  className="text-sky-600 font-semibold disabled:opacity-50">
                  {verifying === a.id ? 'Verifying…' : 'Verify'}
                </button>
              </div>
              {result && (
                <div className={`mt-1.5 px-2 py-1 rounded font-semibold ${
                  result.verified ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
                  {result.verified ? '✓ ' : '✗ '}{result.detail}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </Card>
  )
}

function DisasterPanel() {
  const [advisories, setAdvisories] = useState([])

  useEffect(() => {
    const load = () => api.get('/disasters').then((r) => setAdvisories(r.data))
    load()
    const iv = setInterval(load, 30000)
    return () => clearInterval(iv)
  }, [])

  return (
    <Card title="Disaster & Weather Alert Feeds">
      <p className="text-xs text-slate-500 mb-3">
        Area-level hazard advisories, auto-generated per zone and pushed to every
        tourist inside an affected zone.
      </p>
      <div className="space-y-1.5">
        {advisories.length === 0 && <div className="text-sm text-slate-400">No active advisories.</div>}
        {advisories.map((a) => (
          <div key={a.id} className="flex items-center justify-between text-sm border-b border-slate-50 pb-1.5 last:border-0">
            <span>{HAZARD_ICON[a.hazard_type] || '⚠️'} <span className="font-medium capitalize">{a.hazard_type}</span> — {a.message}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${
              a.severity === 'critical' ? 'bg-red-100 text-red-700' :
              a.severity === 'high' ? 'bg-orange-100 text-orange-700' : 'bg-yellow-100 text-yellow-800'}`}>
              {a.severity}
            </span>
          </div>
        ))}
      </div>
    </Card>
  )
}

export default function AuditLog() {
  const [rows, setRows] = useState([])

  useEffect(() => {
    const load = () => api.get('/audit-log?limit=200').then((r) => setRows(r.data))
    load()
    const iv = setInterval(load, 10000)
    return () => clearInterval(iv)
  }, [])

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold text-slate-800 dark:text-slate-100">Trust, Forensics &amp; Operations</h2>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <AnchorPanel />
        <DisasterPanel />
      </div>

      <Card title="Security Audit Log">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-100">
                <th className="py-2 pr-4">Time</th>
                <th className="py-2 pr-4">Action</th>
                <th className="py-2 pr-4">Actor</th>
                <th className="py-2 pr-4">Target</th>
                <th className="py-2 pr-4">IP</th>
                <th className="py-2 pr-4">Outcome</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan="6" className="py-4 text-slate-400">No audit entries yet.</td></tr>
              )}
              {rows.map((r, i) => (
                <tr key={i} className="border-b border-slate-50 hover:bg-slate-50">
                  <td className="py-2 pr-4 text-slate-500 whitespace-nowrap">{new Date(r.timestamp).toLocaleString()}</td>
                  <td className="py-2 pr-4 font-medium capitalize">{r.action.replace('_', ' ')}</td>
                  <td className="py-2 pr-4">{r.actor}</td>
                  <td className="py-2 pr-4 font-mono text-xs">{r.target || '—'}</td>
                  <td className="py-2 pr-4 font-mono text-xs">{r.ip || '—'}</td>
                  <td className="py-2 pr-4">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${r.outcome === 'success' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                      {r.outcome}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
