import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, Polygon, CircleMarker, useMapEvents } from 'react-leaflet'
import api from '../../api'
import { Card } from '../../components/ui.jsx'
import { riskColor } from '../../components/mapIcons'
import { DEFAULT_MAP, loadMapConfig } from '../../config'

const RISK_LEVELS = ['low', 'medium', 'high', 'restricted']

// Click-to-place-vertex polygon drawing. No external drawing library: a zone
// is just a ring of clicks, "Finish" closes it, "Undo" drops the last point,
// "Cancel" clears it -- simple enough that pulling in leaflet-draw (whose
// React 18 / react-leaflet v4 compatibility is shaky) wasn't worth it.
function DrawCapture({ active, onPoint }) {
  useMapEvents({
    click(e) {
      if (active) onPoint([e.latlng.lat, e.latlng.lng])
    },
  })
  return null
}

const emptyForm = { name: '', risk_level: 'medium', crime_index: 30, description: '' }

const DENSITY_CLS = {
  low: 'bg-green-100 text-green-700',
  medium: 'bg-yellow-100 text-yellow-800',
  high: 'bg-red-100 text-red-700',
}

export default function Zones() {
  const [zones, setZones] = useState([])
  const [mapCfg, setMapCfg] = useState(DEFAULT_MAP)
  const [drawing, setDrawing] = useState(false)
  const [points, setPoints] = useState([])
  const [form, setForm] = useState(emptyForm)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [density, setDensity] = useState([])

  const load = () => api.get('/zones').then((r) => setZones(r.data))
  const loadDensity = () => api.get('/zones/crowd-density').then((r) => setDensity(r.data))

  useEffect(() => {
    load()
    loadDensity()
    loadMapConfig((p) => api.get(p)).then(setMapCfg)
    const iv = setInterval(loadDensity, 15000)
    return () => clearInterval(iv)
  }, [])

  const startDrawing = () => {
    setPoints([])
    setForm(emptyForm)
    setError(null)
    setDrawing(true)
  }

  const cancelDrawing = () => {
    setDrawing(false)
    setPoints([])
  }

  const undoPoint = () => setPoints((p) => p.slice(0, -1))

  const save = async (e) => {
    e.preventDefault()
    if (points.length < 3) {
      setError('A zone needs at least 3 points -- click the map to add more.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await api.post('/zones', {
        ...form,
        crime_index: Number(form.crime_index),
        polygon: points,
      })
      setDrawing(false)
      setPoints([])
      load()
    } catch (err) {
      setError(err.response?.data?.detail?.[0]?.msg || err.response?.data?.detail || 'Failed to save zone.')
    } finally {
      setSaving(false)
    }
  }

  const deleteZone = async (id) => {
    if (!confirm('Delete this zone? This cannot be undone.')) return
    await api.delete(`/zones/${id}`)
    load()
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="lg:col-span-2 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-slate-800 dark:text-slate-100">Risk Zone Editor</h2>
          {!drawing ? (
            <button onClick={startDrawing}
              className="bg-sky-600 hover:bg-sky-700 text-white text-sm font-semibold px-4 py-2 rounded-lg">
              + Draw New Zone
            </button>
          ) : (
            <div className="flex gap-2 text-sm">
              <span className="text-slate-500 self-center">{points.length} point(s) — click the map</span>
              <button onClick={undoPoint} disabled={!points.length}
                className="bg-slate-100 hover:bg-slate-200 disabled:opacity-40 px-3 py-1.5 rounded-lg">Undo</button>
              <button onClick={cancelDrawing}
                className="bg-slate-100 hover:bg-slate-200 px-3 py-1.5 rounded-lg">Cancel</button>
            </div>
          )}
        </div>

        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm overflow-hidden" style={{ height: 560 }}>
          <MapContainer center={mapCfg.center} zoom={mapCfg.zoom} style={{ height: '100%', width: '100%' }} className="map-ops-dark">
            <TileLayer attribution="&copy; OpenStreetMap"
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
            <DrawCapture active={drawing} onPoint={(p) => setPoints((prev) => [...prev, p])} />

            {zones.map((z) => (
              <Polygon key={z.id} positions={z.polygon}
                pathOptions={{ color: riskColor[z.risk_level], fillOpacity: 0.18, weight: 2 }} />
            ))}

            {drawing && points.map((p, i) => (
              <CircleMarker key={i} center={p} radius={5}
                pathOptions={{ color: '#0284c7', fillColor: '#0284c7', fillOpacity: 1 }} />
            ))}
            {drawing && points.length >= 3 && (
              <Polygon positions={points} pathOptions={{ color: '#0284c7', dashArray: '6 4', fillOpacity: 0.1 }} />
            )}
          </MapContainer>
        </div>
      </div>

      <div className="space-y-4">
        {drawing && (
          <Card title="New Zone Details">
            <form onSubmit={save} className="space-y-3 text-sm">
              <div>
                <label className="text-xs text-slate-500">Name</label>
                <input required value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full border border-slate-300 rounded-lg px-2 py-1.5" />
              </div>
              <div>
                <label className="text-xs text-slate-500">Risk Level</label>
                <select value={form.risk_level}
                  onChange={(e) => setForm({ ...form, risk_level: e.target.value })}
                  className="w-full border border-slate-300 rounded-lg px-2 py-1.5 capitalize">
                  {RISK_LEVELS.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-slate-500">Crime Index (0-100)</label>
                <input type="number" min={0} max={100} value={form.crime_index}
                  onChange={(e) => setForm({ ...form, crime_index: e.target.value })}
                  className="w-full border border-slate-300 rounded-lg px-2 py-1.5" />
              </div>
              <div>
                <label className="text-xs text-slate-500">Description</label>
                <textarea value={form.description} rows={2}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  className="w-full border border-slate-300 rounded-lg px-2 py-1.5 resize-none" />
              </div>
              {error && <div className="text-xs text-red-600">{error}</div>}
              <button disabled={saving}
                className="w-full bg-sky-600 hover:bg-sky-700 disabled:opacity-60 text-white font-semibold py-2 rounded-lg">
                {saving ? 'Saving…' : `Save Zone (${points.length} pts)`}
              </button>
            </form>
          </Card>
        )}

        <Card title="Crowd Density">
          <div className="space-y-2 max-h-[220px] overflow-y-auto">
            {density.map((d) => (
              <div key={d.zone_id} className="flex items-center justify-between text-sm">
                <span>{d.zone}</span>
                <span className="flex items-center gap-2">
                  <span className="text-xs text-slate-400">{d.tourist_count} tourists</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${DENSITY_CLS[d.density]}`}>
                    {d.density}{d.overcrowded ? ' ⚠' : ''}
                  </span>
                </span>
              </div>
            ))}
            {density.length === 0 && <div className="text-slate-400 text-sm">No zones yet.</div>}
          </div>
        </Card>

        <Card title="Existing Zones">
          <div className="space-y-2 max-h-[420px] overflow-y-auto">
            {zones.map((z) => (
              <div key={z.id} className="flex items-center justify-between text-sm border-b border-slate-50 pb-2 last:border-0">
                <div>
                  <div className="font-medium flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full inline-block"
                      style={{ background: riskColor[z.risk_level] }}></span>
                    {z.name}
                  </div>
                  <div className="text-xs text-slate-400">
                    {z.risk_level} · crime {z.crime_index} · {z.source}
                  </div>
                </div>
                <button onClick={() => deleteZone(z.id)}
                  className="text-xs text-red-600 hover:underline">delete</button>
              </div>
            ))}
            {zones.length === 0 && <div className="text-slate-400 text-sm">No zones yet.</div>}
          </div>
        </Card>
      </div>
    </div>
  )
}
