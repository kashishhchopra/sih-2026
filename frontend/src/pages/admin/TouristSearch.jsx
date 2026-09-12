import { useEffect, useState } from 'react'
import api from '../../api'
import { ScoreGauge, StatusBadge, Card } from '../../components/ui.jsx'
import TrailReplay from '../../components/TrailReplay.jsx'
import RiskForecastStrip from '../../components/RiskForecastStrip.jsx'

export default function TouristSearch() {
  const [tourists, setTourists] = useState([])
  const [q, setQ] = useState('')
  const [selected, setSelected] = useState(null)
  const [qr, setQr] = useState(null)
  const [chain, setChain] = useState([])
  const [chainValid, setChainValid] = useState(null)
  const [efir, setEfir] = useState(null)
  const [pings, setPings] = useState([])
  const [riskForecast, setRiskForecast] = useState([])

  useEffect(() => { api.get('/tourists').then((r) => setTourists(r.data)) }, [])

  const open = async (t) => {
    setSelected(t); setQr(null); setChain([]); setEfir(null); setChainValid(null); setPings([]); setRiskForecast([])
    const [qrR, chR, vR, pR, fR] = await Promise.all([
      api.get(`/tourists/${t.id}/qr`),
      api.get(`/tourists/${t.id}/chain`),
      api.get(`/tourists/${t.id}/chain/verify`),
      api.get(`/tourists/${t.id}/pings?limit=200`),
      api.get(`/tourists/${t.id}/risk-forecast`),
    ])
    setQr(qrR.data.qr_png_base64)
    setChain(chR.data)
    setChainValid(vR.data.valid)
    setPings(pR.data)
    setRiskForecast(fR.data.forecast)
  }

  const genEfir = async () => {
    const r = await api.post(`/tourists/${selected.id}/mark-missing`)
    setEfir({ ...r.data.efir, id: r.data.efir_id, fir_number: r.data.fir_number })
    setSelected({ ...selected, status: 'missing' })
  }

  const downloadEfirPdf = async () => {
    const { data } = await api.get(`/efirs/${efir.id}/pdf`, { responseType: 'blob' })
    const url = URL.createObjectURL(data)
    window.open(url, '_blank')
    // Revoke shortly after — the new tab has already loaded the blob by then.
    setTimeout(() => URL.revokeObjectURL(url), 30_000)
  }

  const filtered = tourists.filter((t) =>
    !q || t.full_name.toLowerCase().includes(q.toLowerCase()) ||
    t.digital_id.toLowerCase().includes(q.toLowerCase()))

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="lg:col-span-1 space-y-3">
        <input value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="Search by name or digital ID…"
          className="w-full border border-slate-300 rounded-lg px-3 py-2" />
        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm divide-y divide-slate-100 dark:divide-slate-700 max-h-[70vh] overflow-y-auto">
          {filtered.map((t) => (
            <button key={t.id} onClick={() => open(t)}
              className={`w-full text-left px-4 py-3 hover:bg-slate-50 ${selected?.id === t.id ? 'bg-sky-50' : ''}`}>
              <div className="flex items-center justify-between">
                <span className="font-medium">{t.full_name}</span>
                <StatusBadge status={t.status} />
              </div>
              <div className="text-xs text-slate-500">{t.digital_id} · {t.nationality}</div>
            </button>
          ))}
        </div>
      </div>

      <div className="lg:col-span-2">
        {!selected && <Card><div className="text-slate-400 text-sm">Select a tourist to view profile.</div></Card>}
        {selected && (
          <div className="space-y-4">
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm p-4 flex flex-col sm:flex-row gap-4 items-center">
              <ScoreGauge score={selected.safety_score} />
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <h2 className="text-lg font-bold">{selected.full_name}</h2>
                  <StatusBadge status={selected.status} />
                </div>
                <div className="text-sm text-slate-500">{selected.digital_id}</div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 mt-2 text-sm">
                  <div><span className="text-slate-400">Nationality:</span> {selected.nationality}</div>
                  <div><span className="text-slate-400">Doc:</span> {selected.document_type} {selected.document_number}</div>
                  <div><span className="text-slate-400">Phone:</span> {selected.phone}</div>
                  <div><span className="text-slate-400">ID valid:</span> {selected.is_valid ? '✅' : '❌'}</div>
                  <div><span className="text-slate-400">Last seen:</span> {selected.last_seen ? new Date(selected.last_seen).toLocaleString() : '—'}</div>
                  <div><span className="text-slate-400">Location:</span> {selected.last_lat?.toFixed(4)}, {selected.last_lng?.toFixed(4)}</div>
                </div>
              </div>
              {qr && <img src={qr} alt="QR" className="w-28 h-28 border rounded-lg" />}
            </div>

            <RiskForecastStrip forecast={riskForecast} />

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card title="Planned Itinerary">
                <ol className="space-y-1 text-sm list-decimal list-inside">
                  {selected.itinerary?.map((w, i) => <li key={i}>{w.name} <span className="text-slate-400">({w.lat.toFixed(3)}, {w.lng.toFixed(3)})</span></li>)}
                </ol>
              </Card>
              <Card title="Emergency Contacts">
                <ul className="space-y-1 text-sm">
                  {selected.emergency_contacts?.map((c, i) => <li key={i}>{c.name} — {c.phone} <span className="text-slate-400">({c.relation})</span></li>)}
                </ul>
              </Card>
            </div>

            <Card title="Location Trail Replay">
              <TrailReplay pings={pings} />
            </Card>

            <Card title={<span>Digital ID Hash Chain {chainValid != null && (
              <span className={`ml-2 text-xs px-2 py-0.5 rounded-full ${chainValid ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                {chainValid ? '🔒 tamper-proof · verified' : '⚠ broken'}</span>)}</span>}>
              <div className="space-y-1 text-xs font-mono overflow-x-auto">
                {chain.map((b) => (
                  <div key={b.index} className="flex gap-2">
                    <span className="text-slate-400">#{b.index}</span>
                    <span className="text-sky-700">{b.event}</span>
                    <span className="text-slate-400 truncate">{b.hash.slice(0, 24)}…</span>
                  </div>
                ))}
              </div>
            </Card>

            <div className="flex gap-2">
              <button onClick={genEfir}
                className="bg-red-600 hover:bg-red-700 text-white text-sm font-semibold px-4 py-2 rounded-lg">
                Mark Missing &amp; Generate E-FIR
              </button>
            </div>

            {efir && (
              <Card title={`E-FIR — ${efir.fir_number}`}
                actions={
                  <button onClick={downloadEfirPdf}
                    className="text-xs bg-slate-800 hover:bg-slate-700 text-white font-semibold px-3 py-1.5 rounded-lg">
                    Download PDF
                  </button>
                }>
                <div className="text-sm space-y-2">
                  <div className="inline-block bg-green-100 text-green-800 text-xs px-2 py-0.5 rounded-full">
                    FILED · hash-chained to digital ID
                  </div>
                  <p className="text-slate-700 leading-relaxed">{efir.narrative}</p>
                  <div className="mt-2">
                    <div className="font-semibold text-slate-700 mb-1">Anomaly / Alert Timeline</div>
                    {efir.anomaly_timeline.length === 0 && <div className="text-slate-400 text-xs">No prior anomalies recorded.</div>}
                    <ul className="text-xs space-y-1">
                      {efir.anomaly_timeline.map((e, i) => (
                        <li key={i} className="text-slate-600">
                          <span className="text-slate-400">{new Date(e.time).toLocaleString()}</span> — [{e.severity}] {e.message}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </Card>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
