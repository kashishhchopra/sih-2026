import { useEffect, useState } from 'react'
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, LabelList,
} from 'recharts'
import { MapContainer, TileLayer } from 'react-leaflet'
import api from '../../api'
import { Card, Stat } from '../../components/ui.jsx'
import { downloadCSV } from '../../lib/csv'
import { getCctvNetwork } from '../../lib/cctvService'
import HeatmapLayer from '../../components/HeatmapLayer.jsx'
import { DEFAULT_MAP, loadMapConfig } from '../../config'

// Validated categorical order (dataviz reference palette) — assigned by fixed order, never cycled.
const CATEGORICAL = ['#2a78d6', '#008300', '#e87ba4', '#eda100', '#1baf7a', '#eb6834', '#4a3aa7', '#e34948']
// Reserved status palette — severity is a state, not a series.
const STATUS = { low: '#0ca30c', medium: '#fab219', high: '#ec835a', critical: '#d03b3b' }
// Sequential blue ramp for magnitude (crime index).
const SEQ = ['#cde2fb', '#9ec5f4', '#5598e7', '#2a78d6', '#184f95']

const INK = { grid: '#e1e0d9', axis: '#898781', text: '#52514e' }

function seqColor(v, max) {
  const i = Math.min(SEQ.length - 1, Math.floor((v / (max || 1)) * SEQ.length))
  return SEQ[i]
}

function ExportButton({ filename, rows }) {
  return (
    <button onClick={() => downloadCSV(filename, rows)} disabled={!rows?.length}
      className="text-xs text-sky-600 hover:text-sky-700 font-semibold disabled:opacity-30 disabled:cursor-not-allowed">
      ⭳ CSV
    </button>
  )
}

// One-click printable report -- the visual counterpart to the per-chart CSV
// exports above. GET /analytics/pdf renders the same aggregates server-side.
function PdfExportButton() {
  const [loading, setLoading] = useState(false)
  const download = async () => {
    setLoading(true)
    try {
      const { data } = await api.get('/analytics/pdf', { responseType: 'blob' })
      const url = URL.createObjectURL(data)
      window.open(url, '_blank')
      setTimeout(() => URL.revokeObjectURL(url), 30000)
    } finally {
      setLoading(false)
    }
  }
  return (
    <button onClick={download} disabled={loading}
      className="text-sm text-sky-600 hover:text-sky-700 font-semibold disabled:opacity-50">
      {loading ? 'Generating…' : '⭳ Download PDF Report'}
    </button>
  )
}

// Excel counterpart: GET /analytics/excel, same aggregates, one workbook.
function ExcelExportButton() {
  const [loading, setLoading] = useState(false)
  const download = async () => {
    setLoading(true)
    try {
      const { data } = await api.get('/analytics/excel', { responseType: 'blob' })
      const url = URL.createObjectURL(data)
      const a = document.createElement('a')
      a.href = url
      a.download = `analytics-report-${new Date().toISOString().slice(0, 10)}.xlsx`
      document.body.appendChild(a)
      a.click()
      a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 30000)
    } finally {
      setLoading(false)
    }
  }
  return (
    <button onClick={download} disabled={loading}
      className="text-sm text-emerald-600 hover:text-emerald-700 font-semibold disabled:opacity-50">
      {loading ? 'Generating…' : '⭳ Download Excel Report'}
    </button>
  )
}

const GRANULARITIES = [
  { key: 'day', label: 'Daily' },
  { key: 'week', label: 'Weekly' },
  { key: 'month', label: 'Monthly' },
]

export default function Analytics() {
  const [summary, setSummary] = useState(null)
  const [overTime, setOverTime] = useState([])
  const [granularity, setGranularity] = useState('day')
  const [byType, setByType] = useState([])
  const [zoneRisk, setZoneRisk] = useState([])
  const [severity, setSeverity] = useState([])
  const [incidentTypes, setIncidentTypes] = useState(null)
  const [heatmapPoints, setHeatmapPoints] = useState([])
  const [mapCfg, setMapCfg] = useState(DEFAULT_MAP)
  const [policePerf, setPolicePerf] = useState(null)
  const [touristActivity, setTouristActivity] = useState(null)
  const [cctv, setCctv] = useState(null)
  const [mlStatus, setMlStatus] = useState(null)
  const [crowdDensity, setCrowdDensity] = useState([])

  // Everything except the trend chart (which re-fetches on its own when
  // `granularity` changes) loads once -- these aggregates don't depend on it.
  useEffect(() => {
    Promise.all([
      api.get('/analytics/summary'),
      api.get('/analytics/alerts-by-type'),
      api.get('/analytics/zone-risk'),
      api.get('/analytics/severity-breakdown'),
      api.get('/analytics/incident-types'),
      api.get('/analytics/incidents-heatmap'),
      api.get('/analytics/police-performance'),
      api.get('/analytics/tourist-activity'),
      api.get('/zones/crowd-density'),
      api.get('/ml/status'),
      getCctvNetwork(),
    ]).then(([s, t, z, sev, types, heat, perf, tourists, density, ml, cctvNet]) => {
      setSummary(s.data); setByType(t.data)
      setZoneRisk(z.data); setSeverity(sev.data)
      setIncidentTypes(types.data)
      setHeatmapPoints(heat.data.map((p) => [p.lat, p.lng, 1]))
      setPolicePerf(perf.data)
      setTouristActivity(tourists.data)
      setCrowdDensity(density.data)
      setMlStatus(ml.data)
      setCctv(cctvNet)
    })
    loadMapConfig((p) => api.get(p)).then(setMapCfg)
  }, [])

  useEffect(() => {
    api.get('/analytics/incidents-over-time', { params: { granularity } })
      .then(({ data }) => setOverTime(data))
  }, [granularity])

  const maxCrime = Math.max(1, ...zoneRisk.map((z) => z.crime_index))
  const maxDensity = Math.max(1, ...crowdDensity.map((d) => d.tourist_count || 0))

  const nationalityRows = touristActivity ? [
    { group: 'Domestic', count: touristActivity.domestic_tourists },
    { group: 'International', count: touristActivity.international_tourists },
  ] : []

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="text-lg font-bold text-slate-800 dark:text-slate-100">Analytics &amp; Reporting</h2>
        <div className="flex items-center gap-3">
          <ExcelExportButton />
          <PdfExportButton />
        </div>
      </div>

      {/* ---- top-level KPIs ---- */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="Total Incidents" value={summary.total_incidents} />
          <Stat label="Avg Response Time" value={`${Math.round(summary.avg_response_time_seconds)}s`} />
          <Stat label="Active Alerts" value={summary.active_alerts} accent="text-orange-600" />
          <Stat label="Risk Zones" value={summary.total_zones} />
        </div>
      )}

      {/* ---- 🚨 SOS & Emergency Analytics ---- */}
      <div>
        <h3 className="text-sm font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wide mb-2">
          🚨 SOS &amp; Emergency Analytics
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="Total SOS Cases" value={incidentTypes?.sos.total ?? '—'} />
          <Stat label="Active SOS" value={incidentTypes?.sos.active ?? '—'} accent="text-red-600" />
          <Stat label="Resolved SOS" value={incidentTypes?.sos.resolved ?? '—'} accent="text-emerald-600" />
          <Stat label="Avg Police Response"
            value={summary ? `${Math.round(summary.avg_response_time_seconds)}s` : '—'} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Incidents Over Time" actions={
          <div className="flex items-center gap-2">
            <div className="flex rounded-lg overflow-hidden border border-slate-200 dark:border-slate-600">
              {GRANULARITIES.map((g) => (
                <button key={g.key} onClick={() => setGranularity(g.key)}
                  className={`px-2 py-0.5 text-[11px] font-semibold ${
                    granularity === g.key
                      ? 'bg-sky-600 text-white'
                      : 'bg-white dark:bg-slate-800 text-slate-500 dark:text-slate-400'}`}>
                  {g.label}
                </button>
              ))}
            </div>
            <ExportButton filename={`incidents-over-time-${granularity}`} rows={overTime} />
          </div>
        }>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={overTime} margin={{ top: 10, right: 16, bottom: 0, left: -16 }}>
              <CartesianGrid stroke={INK.grid} vertical={false} />
              <XAxis dataKey="date" tick={{ fill: INK.axis, fontSize: 12 }} tickLine={false} />
              <YAxis allowDecimals={false} tick={{ fill: INK.axis, fontSize: 12 }} tickLine={false} axisLine={false} />
              <Tooltip />
              <Line type="monotone" dataKey="count" name="Incidents" stroke={CATEGORICAL[0]}
                strokeWidth={2} dot={{ r: 3, fill: CATEGORICAL[0] }} />
            </LineChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Most Common Incident Types"
          actions={<ExportButton filename="incident-types" rows={incidentTypes?.by_type} />}>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={incidentTypes?.by_type || []} margin={{ top: 16, right: 16, bottom: 0, left: -16 }}>
              <CartesianGrid stroke={INK.grid} vertical={false} />
              <XAxis dataKey="type" tick={{ fill: INK.axis, fontSize: 11 }} tickLine={false} />
              <YAxis allowDecimals={false} tick={{ fill: INK.axis, fontSize: 12 }} tickLine={false} axisLine={false} />
              <Tooltip cursor={{ fill: 'rgba(0,0,0,0.04)' }} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {(incidentTypes?.by_type || []).map((_, i) => <Cell key={i} fill={CATEGORICAL[i % CATEGORICAL.length]} />)}
                <LabelList dataKey="count" position="top" fill={INK.text} fontSize={11} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Alerts by Type" actions={<ExportButton filename="alerts-by-type" rows={byType} />}>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={byType} margin={{ top: 16, right: 16, bottom: 0, left: -16 }}>
              <CartesianGrid stroke={INK.grid} vertical={false} />
              <XAxis dataKey="type" tick={{ fill: INK.axis, fontSize: 11 }} tickLine={false} />
              <YAxis allowDecimals={false} tick={{ fill: INK.axis, fontSize: 12 }} tickLine={false} axisLine={false} />
              <Tooltip cursor={{ fill: 'rgba(0,0,0,0.04)' }} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {byType.map((_, i) => <Cell key={i} fill={CATEGORICAL[i % CATEGORICAL.length]} />)}
                <LabelList dataKey="count" position="top" fill={INK.text} fontSize={11} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Incident Severity Breakdown" actions={<ExportButton filename="severity-breakdown" rows={severity} />}>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={severity} margin={{ top: 16, right: 16, bottom: 0, left: -16 }}>
              <CartesianGrid stroke={INK.grid} vertical={false} />
              <XAxis dataKey="severity" tick={{ fill: INK.axis, fontSize: 12 }} tickLine={false} />
              <YAxis allowDecimals={false} tick={{ fill: INK.axis, fontSize: 12 }} tickLine={false} axisLine={false} />
              <Tooltip cursor={{ fill: 'rgba(0,0,0,0.04)' }} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {severity.map((s, i) => <Cell key={i} fill={STATUS[s.severity] || '#898781'} />)}
                <LabelList dataKey="count" position="top" fill={INK.text} fontSize={11} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="flex gap-3 mt-2 text-xs text-slate-500 flex-wrap">
            {Object.entries(STATUS).map(([k, v]) => (
              <span key={k} className="flex items-center gap-1">
                <span className="w-3 h-3 rounded-sm inline-block" style={{ background: v }}></span>{k}
              </span>
            ))}
          </div>
        </Card>
      </div>

      {/* ---- 🗺️ Crime & Safety Hotspots ---- */}
      <h3 className="text-sm font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wide pt-2">
        🗺️ Crime &amp; Safety Hotspots
      </h3>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Incident Density Heatmap">
          <div className="rounded-lg overflow-hidden" style={{ height: 280 }}>
            <MapContainer center={mapCfg.center} zoom={mapCfg.zoom} style={{ height: '100%', width: '100%' }} className="map-ops-dark">
              <TileLayer attribution="&copy; OpenStreetMap"
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
              <HeatmapLayer points={heatmapPoints} />
            </MapContainer>
          </div>
          {heatmapPoints.length === 0 && (
            <div className="text-xs text-slate-400 mt-2">No located incidents yet.</div>
          )}
        </Card>

        <Card title="Zone-wise Crime Index (higher = riskier)" actions={<ExportButton filename="zone-risk" rows={zoneRisk} />}>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={zoneRisk} layout="vertical" margin={{ top: 4, right: 24, bottom: 0, left: 8 }}>
              <CartesianGrid stroke={INK.grid} horizontal={false} />
              <XAxis type="number" domain={[0, 100]} tick={{ fill: INK.axis, fontSize: 12 }} tickLine={false} axisLine={false} />
              <YAxis type="category" dataKey="zone" width={150} tick={{ fill: INK.text, fontSize: 11 }} tickLine={false} axisLine={false} />
              <Tooltip cursor={{ fill: 'rgba(0,0,0,0.04)' }} />
              <Bar dataKey="crime_index" radius={[0, 4, 4, 0]}>
                {zoneRisk.map((z, i) => <Cell key={i} fill={seqColor(z.crime_index, maxCrime)} />)}
                <LabelList dataKey="crime_index" position="right" fill={INK.text} fontSize={11} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* ---- 👮 Police Performance ---- */}
      <h3 className="text-sm font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wide pt-2">
        👮 Police Performance
      </h3>
      <Card title="Cases by Station"
        actions={<ExportButton filename="police-performance" rows={policePerf?.stations} />}>
        {policePerf && policePerf.stations.length === 0 && (
          <div className="text-sm text-slate-400">No stations registered yet.</div>
        )}
        {policePerf && policePerf.stations.length > 0 && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-500 dark:text-slate-400 border-b border-slate-100 dark:border-slate-700">
                    <th className="pb-2 pr-3">Station</th>
                    <th className="pb-2 pr-3 text-right">Cases</th>
                    <th className="pb-2 pr-3 text-right">Pending</th>
                    <th className="pb-2 pr-3 text-right">Resolved</th>
                    <th className="pb-2 pr-3 text-right">Avg Response</th>
                    <th className="pb-2 pr-3 text-right">Avg Resolution</th>
                    <th className="pb-2 text-right">Transfers In</th>
                  </tr>
                </thead>
                <tbody>
                  {policePerf.stations.map((s) => (
                    <tr key={s.station_id} className="border-b border-slate-50 dark:border-slate-800">
                      <td className="py-1.5 pr-3 font-medium text-slate-800 dark:text-slate-100">{s.station}</td>
                      <td className="py-1.5 pr-3 text-right">{s.cases_handled}</td>
                      <td className="py-1.5 pr-3 text-right text-orange-600">{s.pending}</td>
                      <td className="py-1.5 pr-3 text-right text-emerald-600">{s.resolved}</td>
                      <td className="py-1.5 pr-3 text-right">
                        {s.avg_response_time_seconds != null ? `${Math.round(s.avg_response_time_seconds)}s` : '—'}
                      </td>
                      <td className="py-1.5 pr-3 text-right">
                        {s.avg_resolution_time_seconds != null ? `${Math.round(s.avg_resolution_time_seconds / 60)}m` : '—'}
                      </td>
                      <td className="py-1.5 text-right">{s.transfers_received}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="text-xs text-slate-400 mt-2">
              {policePerf.total_transfers} inter-station case transfer{policePerf.total_transfers === 1 ? '' : 's'} network-wide.
            </div>
          </>
        )}
      </Card>

      {/* ---- 👥 Tourist Activity Analytics ---- */}
      <h3 className="text-sm font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wide pt-2">
        👥 Tourist Activity Analytics
      </h3>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {touristActivity && (
          <div className="grid grid-cols-2 gap-3 content-start">
            <Stat label="Total Tourists" value={touristActivity.total_tourists} />
            <Stat label="Active Tourists" value={touristActivity.active_tourists} accent="text-emerald-600" />
            <Stat label="Domestic" value={touristActivity.domestic_tourists} />
            <Stat label="International" value={touristActivity.international_tourists} />
          </div>
        )}

        <Card title="Domestic vs. International" actions={<ExportButton filename="tourist-nationality" rows={nationalityRows} />}>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={nationalityRows} margin={{ top: 16, right: 16, bottom: 0, left: -16 }}>
              <CartesianGrid stroke={INK.grid} vertical={false} />
              <XAxis dataKey="group" tick={{ fill: INK.axis, fontSize: 12 }} tickLine={false} />
              <YAxis allowDecimals={false} tick={{ fill: INK.axis, fontSize: 12 }} tickLine={false} axisLine={false} />
              <Tooltip cursor={{ fill: 'rgba(0,0,0,0.04)' }} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {nationalityRows.map((_, i) => <Cell key={i} fill={CATEGORICAL[i]} />)}
                <LabelList dataKey="count" position="top" fill={INK.text} fontSize={11} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Popular Destinations (confirmed itineraries)"
          actions={<ExportButton filename="popular-destinations" rows={touristActivity?.popular_destinations} />}>
          {touristActivity && touristActivity.popular_destinations.length === 0 ? (
            <div className="text-sm text-slate-400">No confirmed itinerary destinations yet.</div>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={touristActivity?.popular_destinations || []} layout="vertical"
                margin={{ top: 4, right: 24, bottom: 0, left: 8 }}>
                <CartesianGrid stroke={INK.grid} horizontal={false} />
                <XAxis type="number" allowDecimals={false} tick={{ fill: INK.axis, fontSize: 12 }} tickLine={false} axisLine={false} />
                <YAxis type="category" dataKey="destination" width={140} tick={{ fill: INK.text, fontSize: 11 }} tickLine={false} axisLine={false} />
                <Tooltip cursor={{ fill: 'rgba(0,0,0,0.04)' }} />
                <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                  {(touristActivity?.popular_destinations || []).map((_, i) => <Cell key={i} fill={CATEGORICAL[i % CATEGORICAL.length]} />)}
                  <LabelList dataKey="count" position="right" fill={INK.text} fontSize={11} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Tourist Density by Zone" actions={<ExportButton filename="tourist-density" rows={crowdDensity} />}>
          {crowdDensity.length === 0 ? (
            <div className="text-sm text-slate-400">No zone activity yet.</div>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={crowdDensity} layout="vertical" margin={{ top: 4, right: 24, bottom: 0, left: 8 }}>
                <CartesianGrid stroke={INK.grid} horizontal={false} />
                <XAxis type="number" allowDecimals={false} tick={{ fill: INK.axis, fontSize: 12 }} tickLine={false} axisLine={false} />
                <YAxis type="category" dataKey="zone" width={140} tick={{ fill: INK.text, fontSize: 11 }} tickLine={false} axisLine={false} />
                <Tooltip cursor={{ fill: 'rgba(0,0,0,0.04)' }} />
                <Bar dataKey="tourist_count" radius={[0, 4, 4, 0]}>
                  {crowdDensity.map((d, i) => <Cell key={i} fill={seqColor(d.tourist_count || 0, maxDensity)} />)}
                  <LabelList dataKey="tourist_count" position="right" fill={INK.text} fontSize={11} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      {/* ---- 📹 CCTV & AI Analytics ---- */}
      <h3 className="text-sm font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wide pt-2">
        📹 CCTV &amp; AI Analytics
      </h3>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Cameras Live" value={cctv?.summary.live ?? '—'} accent="text-emerald-600" />
        <Stat label="Cameras Offline" value={cctv?.summary.offline ?? '—'} accent="text-slate-500" />
        <Stat label="AI Anomalies Flagged" value={mlStatus?.anomalies_flagged ?? '—'} accent="text-orange-600" />
        <Stat label="Live Location Pings" value={mlStatus?.live_pings_collected ?? '—'} />
      </div>
      <div className="text-xs text-slate-400">
        {cctv?.summary.total ?? 0} camera{cctv?.summary.total === 1 ? '' : 's'} registered
        {cctv?.summary.no_stream ? `, ${cctv.summary.no_stream} without a configured feed` : ''}
        {cctv?.summary.unavailable ? `, ${cctv.summary.unavailable} publishing an unavailable notice` : ''}.
        {' '}AI inference mode: {mlStatus?.inference_mode || '—'}.
      </div>
    </div>
  )
}
