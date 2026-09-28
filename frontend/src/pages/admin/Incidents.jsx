import { useEffect, useMemo, useState } from 'react'
import api from '../../api'
import useWebSocket from '../../useWebSocket'
import { SeverityBadge, StatusBadge, Card } from '../../components/ui.jsx'
import DispatchPanel from '../../components/DispatchPanel.jsx'
import IncidentTimeline from '../../components/IncidentTimeline.jsx'
import TouristDetailsPanel from '../../components/TouristDetailsPanel.jsx'
import { downloadCSV } from '../../lib/csv'

const NEXT = { detected: 'acknowledged', acknowledged: 'dispatched', dispatched: 'resolved' }
const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3 }

const SORTERS = {
  newest: (a, b) => new Date(b.detected_at) - new Date(a.detected_at),
  oldest: (a, b) => new Date(a.detected_at) - new Date(b.detected_at),
  severity: (a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9),
  response_time: (a, b) =>
    (b.response_time_seconds ?? -1) - (a.response_time_seconds ?? -1),
}

export default function Incidents() {
  const [incidents, setIncidents] = useState([])
  const [statusFilter, setStatusFilter] = useState('')
  const [severityFilter, setSeverityFilter] = useState('')
  const [sortBy, setSortBy] = useState('newest')
  const [expanded, setExpanded] = useState(null)
  const [expandedTab, setExpandedTab] = useState('dispatch')

  const load = () => {
    const url = statusFilter ? `/incidents?status=${statusFilter}` : '/incidents'
    api.get(url).then((r) => setIncidents(r.data))
  }
  useEffect(load, [statusFilter])
  useWebSocket((ev) => { if (ev.event === 'incident') load() })

  const advance = async (inc) => {
    const next = NEXT[inc.status]
    if (!next) return
    await api.patch(`/incidents/${inc.id}`, { status: next, note: `Advanced to ${next} by operator` })
    load()
  }

  const fmt = (s) => s == null ? '—' : `${Math.round(s)}s`

  const visible = useMemo(() => {
    const filtered = severityFilter
      ? incidents.filter((i) => i.severity === severityFilter)
      : incidents
    return [...filtered].sort(SORTERS[sortBy])
  }, [incidents, severityFilter, sortBy])

  const exportCSV = () => downloadCSV('incidents', visible.map((inc) => ({
    id: inc.id,
    tourist_name: inc.tourist_name,
    tourist_digital_id: inc.tourist_digital_id,
    type: inc.type,
    severity: inc.severity,
    status: inc.status,
    description: inc.description,
    detected_at: inc.detected_at,
    resolved_at: inc.resolved_at,
    response_time_seconds: inc.response_time_seconds,
    lat: inc.lat,
    lng: inc.lng,
  })))

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold text-slate-800 dark:text-slate-100">Incident Response Workflow</h2>
        <div className="flex items-center gap-2 flex-wrap">
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
            className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm">
            <option value="">All statuses</option>
            <option value="detected">Detected</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="dispatched">Dispatched</option>
            <option value="resolved">Resolved</option>
          </select>
          <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)}
            className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm">
            <option value="">All severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}
            className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm">
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
            <option value="severity">Most severe first</option>
            <option value="response_time">Slowest response first</option>
          </select>
          <button onClick={exportCSV} disabled={!visible.length}
            className="text-sm text-sky-600 hover:text-sky-700 font-semibold disabled:opacity-30 disabled:cursor-not-allowed">
            ⭳ Export CSV
          </button>
        </div>
      </div>

      <div className="space-y-3">
        {visible.length === 0 && <Card><div className="text-slate-400 text-sm">No incidents match this filter.</div></Card>}
        {visible.map((inc) => (
          <div key={inc.id} className="bg-white dark:bg-slate-800 rounded-xl shadow-sm p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold">#{inc.id}</span>
                {inc.tourist_name && (
                  <span className="text-sm text-slate-700 dark:text-slate-200">{inc.tourist_name}</span>
                )}
                <span className="capitalize">{inc.type.replace('_', ' ')}</span>
                <SeverityBadge severity={inc.severity} />
                <StatusBadge status={inc.status} />
                {inc.escalation_stage && <StatusBadge status={inc.escalation_stage} />}
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => { setExpanded(expanded === inc.id ? null : inc.id); setExpandedTab('dispatch') }}
                  className="text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 text-xs font-semibold px-2 py-1.5">
                  {expanded === inc.id ? 'Hide details ▲' : 'Details ▾'}
                </button>
                {NEXT[inc.status] && (
                  <button onClick={() => advance(inc)}
                    className="bg-sky-600 hover:bg-sky-700 text-white text-xs font-semibold px-3 py-1.5 rounded-lg">
                    → {NEXT[inc.status]}
                  </button>
                )}
              </div>
            </div>
            <div className="text-sm text-slate-600 mt-1">{inc.description}</div>
            <div className="flex flex-wrap gap-x-6 gap-y-1 mt-2 text-xs text-slate-500">
              <span>Detected: {new Date(inc.detected_at).toLocaleString()}</span>
              <span>Response time: {fmt(inc.response_time_seconds)}</span>
              {inc.lat && <span>Loc: {inc.lat.toFixed(4)}, {inc.lng.toFixed(4)}</span>}
            </div>
            {/* lifecycle progress */}
            <div className="flex items-center gap-1 mt-3">
              {['detected', 'acknowledged', 'dispatched', 'resolved'].map((s, i) => {
                const order = ['detected', 'acknowledged', 'dispatched', 'resolved']
                const done = order.indexOf(inc.status) >= i
                return (
                  <div key={s} className="flex-1 flex items-center">
                    <div className={`h-1.5 flex-1 rounded ${done ? 'bg-sky-500' : 'bg-slate-200'}`}></div>
                  </div>
                )
              })}
            </div>
            <div className="flex justify-between text-[10px] text-slate-400 mt-1">
              <span>Detected</span><span>Ack</span><span>Dispatched</span><span>Resolved</span>
            </div>
            {expanded === inc.id && (
              <div className="mt-3 pt-3 border-t border-slate-100 dark:border-slate-700">
                <div className="flex items-center gap-1 mb-3">
                  {['dispatch', 'timeline', 'tourist'].map((tab) => (
                    <button key={tab} onClick={() => setExpandedTab(tab)}
                      className={`text-xs font-semibold px-3 py-1 rounded-lg capitalize ${
                        expandedTab === tab ? 'bg-sky-600 text-white' : 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300'}`}>
                      {tab}
                    </button>
                  ))}
                </div>
                {expandedTab === 'dispatch' && <DispatchPanel incidentId={inc.id} />}
                {expandedTab === 'timeline' && (
                  <IncidentTimeline incidentId={inc.id} touristId={inc.tourist_id} />
                )}
                {expandedTab === 'tourist' && <TouristDetailsPanel touristId={inc.tourist_id} />}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
