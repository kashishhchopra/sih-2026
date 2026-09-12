import { useEffect, useState } from 'react'
import api from '../../api'
import { Card } from '../../components/ui.jsx'

export default function Devices() {
  const [devices, setDevices] = useState([])
  const [tourists, setTourists] = useState([])
  const [form, setForm] = useState({ tourist_id: '', device_id: '', firmware_version: '1.0.0' })
  const [issuedKey, setIssuedKey] = useState(null)
  const [error, setError] = useState(null)

  const load = () => api.get('/devices').then((r) => setDevices(r.data))

  useEffect(() => {
    load()
    api.get('/tourists').then((r) => setTourists(r.data))
  }, [])

  const register = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      const { data } = await api.post('/devices/register', {
        ...form, tourist_id: Number(form.tourist_id),
      })
      setIssuedKey(data)
      setForm({ tourist_id: '', device_id: '', firmware_version: '1.0.0' })
      load()
    } catch (err) {
      setError(err.response?.data?.detail || 'Registration failed.')
    }
  }

  const deactivate = async (deviceId) => {
    await api.post(`/devices/${deviceId}/deactivate`)
    load()
  }

  const nameFor = (id) => tourists.find((t) => t.id === id)?.full_name || `#${id}`

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold text-slate-800 dark:text-slate-100">IoT Smart-Band Devices</h2>

      {issuedKey && (
        <div className="bg-amber-50 border border-amber-300 rounded-xl p-4 text-sm">
          <div className="font-semibold text-amber-800">
            Device {issuedKey.device_id} registered — copy this API key now, it will not be shown again:
          </div>
          <code className="block mt-2 bg-white dark:bg-slate-900 border border-amber-200 dark:border-amber-800 rounded-lg p-2 text-xs break-all">
            {issuedKey.api_key}
          </code>
          <button onClick={() => setIssuedKey(null)} className="text-xs text-amber-700 mt-2 underline">
            Dismiss
          </button>
        </div>
      )}

      <Card title="Register a Band">
        <form onSubmit={register} className="grid grid-cols-1 sm:grid-cols-4 gap-3 items-end">
          <div>
            <label className="text-xs text-slate-500">Tourist</label>
            <select required value={form.tourist_id}
              onChange={(e) => setForm({ ...form, tourist_id: e.target.value })}
              className="w-full border border-slate-300 rounded-lg px-2 py-1.5 text-sm">
              <option value="">Select…</option>
              {tourists.map((t) => (
                <option key={t.id} value={t.id}>{t.full_name} ({t.digital_id})</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500">Device ID</label>
            <input required minLength={4} value={form.device_id}
              onChange={(e) => setForm({ ...form, device_id: e.target.value })}
              placeholder="BAND-0042"
              className="w-full border border-slate-300 rounded-lg px-2 py-1.5 text-sm" />
          </div>
          <div>
            <label className="text-xs text-slate-500">Firmware</label>
            <input value={form.firmware_version}
              onChange={(e) => setForm({ ...form, firmware_version: e.target.value })}
              className="w-full border border-slate-300 rounded-lg px-2 py-1.5 text-sm" />
          </div>
          <button className="bg-sky-600 hover:bg-sky-700 text-white text-sm font-semibold px-4 py-2 rounded-lg">
            Register
          </button>
        </form>
        {error && <div className="text-xs text-red-600 mt-2">{error}</div>}
      </Card>

      <Card title="Device Roster">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500 border-b border-slate-100">
                <th className="py-2 pr-4">Device</th>
                <th className="py-2 pr-4">Tourist</th>
                <th className="py-2 pr-4">Firmware</th>
                <th className="py-2 pr-4">Battery</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2 pr-4">Last Heartbeat</th>
                <th className="py-2"></th>
              </tr>
            </thead>
            <tbody>
              {devices.length === 0 && (
                <tr><td colSpan={7} className="py-4 text-center text-slate-400">No devices registered.</td></tr>
              )}
              {devices.map((d) => (
                <tr key={d.device_id} className="border-b border-slate-50">
                  <td className="py-2 pr-4 font-mono text-xs">{d.device_id}</td>
                  <td className="py-2 pr-4">{nameFor(d.tourist_id)}</td>
                  <td className="py-2 pr-4 text-slate-500">{d.firmware_version}</td>
                  <td className="py-2 pr-4">
                    {d.battery_pct != null ? (
                      <span className={d.battery_pct < 20 ? 'text-red-600 font-semibold' : ''}>
                        {d.battery_pct.toFixed(0)}%
                      </span>
                    ) : '—'}
                  </td>
                  <td className="py-2 pr-4">
                    {!d.active ? (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">deactivated</span>
                    ) : d.is_online ? (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700">online</span>
                    ) : (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700">offline</span>
                    )}
                  </td>
                  <td className="py-2 pr-4 text-xs text-slate-500">
                    {d.last_heartbeat ? new Date(d.last_heartbeat).toLocaleTimeString() : '—'}
                  </td>
                  <td className="py-2">
                    {d.active && (
                      <button onClick={() => deactivate(d.device_id)}
                        className="text-xs text-red-600 hover:underline">deactivate</button>
                    )}
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
