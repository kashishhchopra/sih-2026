import { useEffect, useRef, useState } from 'react'
import jsQR from 'jsqr'
import api from '../api'
import { Card } from './ui.jsx'

// Digital Tourist Safety ID scanner: camera QR scan or manual Tourist ID
// entry -- both funnel into the same authorized POST /tourist-id/scan, so a
// device without camera support is never blocked from verifying someone.
// See backend/app/services/tourist_id.py for what each caller's role is
// allowed to see back.
//
// The camera path decodes frames with jsQR (a pure-JS decoder) rather than
// the native BarcodeDetector API -- BarcodeDetector only ships in
// Chromium-based browsers (not Safari, not Firefox), which would silently
// break scanning for a large share of real devices.
//
// `renderActions(result)` lets each host page (admin / responder) add its
// own role-appropriate buttons under a verified result without this
// component needing to know about incidents, trip pages, etc.
export default function TouristIdScanner({ renderActions }) {
  const [mode, setMode] = useState('manual') // 'camera' | 'manual'
  const [manualId, setManualId] = useState('')
  const [phase, setPhase] = useState('idle') // idle | scanning | verifying | done
  const [result, setResult] = useState(null)
  const [cameraError, setCameraError] = useState('')
  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const streamRef = useRef(null)
  const rafRef = useRef(null)
  const verifyingRef = useRef(false)

  const stopCamera = () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    rafRef.current = null
    verifyingRef.current = false
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
  }

  useEffect(() => () => stopCamera(), [])

  const verify = async (payload) => {
    setPhase('verifying')
    try {
      const { data } = await api.post('/tourist-id/scan', payload)
      setResult(data)
    } catch {
      setResult({ verification_status: 'invalid', reason: 'Could not reach the verification service.' })
    } finally {
      setPhase('done')
      stopCamera()
    }
  }

  const startCamera = async () => {
    setCameraError('')
    setResult(null)
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError('Camera access is not available on this device. Use manual entry below.')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
      }
      setPhase('scanning')
      if (!canvasRef.current) canvasRef.current = document.createElement('canvas')
      const canvas = canvasRef.current
      const ctx = canvas.getContext('2d', { willReadFrequently: true })
      const tick = () => {
        const video = videoRef.current
        if (!video || !streamRef.current) return
        if (video.readyState === video.HAVE_ENOUGH_DATA && !verifyingRef.current) {
          canvas.width = video.videoWidth
          canvas.height = video.videoHeight
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
          const frame = ctx.getImageData(0, 0, canvas.width, canvas.height)
          const code = jsQR(frame.data, frame.width, frame.height)
          if (code?.data) {
            verifyingRef.current = true
            verify({ token: code.data })
            return
          }
        }
        rafRef.current = requestAnimationFrame(tick)
      }
      rafRef.current = requestAnimationFrame(tick)
    } catch {
      setCameraError('Camera access denied or unavailable. Use manual entry below.')
    }
  }

  const switchMode = (next) => {
    stopCamera()
    setPhase('idle')
    setResult(null)
    setCameraError('')
    setMode(next)
    if (next === 'camera') startCamera()
  }

  const submitManual = (e) => {
    e.preventDefault()
    if (!manualId.trim()) return
    verify({ digital_id: manualId.trim() })
  }

  const reset = () => {
    setResult(null)
    setPhase('idle')
    setManualId('')
    if (mode === 'camera') startCamera()
  }

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <button onClick={() => switchMode('camera')}
          className={`flex-1 text-sm font-semibold py-2 rounded-lg ${mode === 'camera' ? 'bg-sky-600 text-white' : 'bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200'}`}>
          📷 Scan QR
        </button>
        <button onClick={() => switchMode('manual')}
          className={`flex-1 text-sm font-semibold py-2 rounded-lg ${mode === 'manual' ? 'bg-sky-600 text-white' : 'bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200'}`}>
          ⌨️ Enter Tourist ID
        </button>
      </div>

      {mode === 'camera' && (
        <div className="space-y-2">
          <div className="relative bg-black rounded-xl overflow-hidden" style={{ aspectRatio: '4/3' }}>
            <video ref={videoRef} muted playsInline className="w-full h-full object-cover opacity-90" />
            {phase === 'scanning' && (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-2/3 aspect-square border-2 border-sky-400/80 rounded-xl" />
              </div>
            )}
          </div>
          {phase === 'scanning' && (
            <div className="text-center text-xs text-slate-400">Point camera at QR code — Scanning…</div>
          )}
          {cameraError && (
            <div className="text-xs text-orange-600 dark:text-orange-400 text-center">{cameraError}</div>
          )}
        </div>
      )}

      {mode === 'manual' && !result && (
        <form onSubmit={submitManual} className="flex gap-2">
          <input value={manualId} onChange={(e) => setManualId(e.target.value)}
            placeholder="e.g. STS-A1B2C3D4E5F6" autoFocus
            className="flex-1 border border-slate-300 dark:border-slate-600 dark:bg-slate-700 rounded-lg px-3 py-2 text-sm font-mono" />
          <button type="submit" disabled={!manualId.trim() || phase === 'verifying'}
            className="bg-sky-600 hover:bg-sky-700 disabled:opacity-40 text-white text-sm font-semibold px-4 rounded-lg">
            Verify
          </button>
        </form>
      )}

      {phase === 'verifying' && (
        <div className="text-center text-sm text-slate-400 py-3">Verifying…</div>
      )}

      {result && (
        <VerifiedResult result={result} onReset={reset} renderActions={renderActions} />
      )}
    </div>
  )
}

const STATUS_META = {
  verified: { icon: '🟢', label: 'TOURIST VERIFIED', cls: 'text-green-600 dark:text-green-400' },
  not_found: { icon: '🔴', label: 'INVALID TOURIST ID', cls: 'text-red-600 dark:text-red-400' },
  invalid: { icon: '🔴', label: 'VERIFICATION FAILED', cls: 'text-red-600 dark:text-red-400' },
  invalidated: { icon: '🔴', label: 'ID INVALIDATED', cls: 'text-red-600 dark:text-red-400' },
  expired: { icon: '⚫', label: 'TOURIST ID EXPIRED', cls: 'text-slate-500 dark:text-slate-400' },
}

function VerifiedResult({ result, onReset, renderActions }) {
  const meta = STATUS_META[result.verification_status] || STATUS_META.invalid
  const isVerified = result.verification_status === 'verified'

  return (
    <Card>
      <div className="text-center mb-3">
        <div className={`text-lg font-bold flex items-center justify-center gap-2 ${meta.cls}`}>
          <span>{meta.icon}</span>{meta.label}
        </div>
        {!isVerified && result.reason && (
          <div className="text-sm text-slate-500 dark:text-slate-400 mt-1">{result.reason}</div>
        )}
      </div>

      {isVerified && (
        <div className="flex gap-4 items-start">
          {result.photo ? (
            <img src={result.photo} alt={result.full_name}
              className="w-20 h-20 rounded-xl object-cover border border-slate-200 dark:border-slate-600 shrink-0" />
          ) : (
            <div className="w-20 h-20 rounded-xl bg-slate-100 dark:bg-slate-700 shrink-0 flex items-center justify-center text-2xl">🪪</div>
          )}
          <div className="text-sm space-y-1 min-w-0">
            <div className="font-bold text-slate-800 dark:text-slate-100 text-base">{result.full_name}</div>
            <div><span className="text-slate-400">Tourist ID:</span> <span className="font-mono">{result.digital_id}</span></div>
            {result.hotel && <div><span className="text-slate-400">Hotel:</span> {result.hotel}</div>}
            {result.current_zone && <div><span className="text-slate-400">Current Zone:</span> {result.current_zone.name}</div>}
            {result.assigned_station && <div><span className="text-slate-400">Assigned Station:</span> {result.assigned_station.name}</div>}
            {result.trip_status && <div><span className="text-slate-400">Trip Status:</span> <span className="capitalize">{result.trip_status}</span></div>}
            {result.trip_start && result.trip_end && (
              <div><span className="text-slate-400">Check-in / out:</span>{' '}
                {new Date(result.trip_start).toLocaleDateString()} → {new Date(result.trip_end).toLocaleDateString()}
              </div>
            )}
            {Array.isArray(result.emergency_contacts) && (
              <div>
                <span className="text-slate-400">Emergency Contact:</span>{' '}
                {result.emergency_contacts.length
                  ? `${result.emergency_contacts[0].name} — ${result.emergency_contacts[0].phone}`
                  : 'None on file'}
              </div>
            )}
            {Array.isArray(result.active_incidents) && result.active_incidents.length > 0 && (
              <div className="text-red-600 dark:text-red-400 font-semibold">
                🚨 {result.active_incidents.length} active incident(s)
              </div>
            )}
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 mt-4 pt-3 border-t border-slate-100 dark:border-slate-700">
        {isVerified && renderActions?.(result)}
        <button onClick={onReset}
          className="ml-auto text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 font-semibold">
          Scan another →
        </button>
      </div>
    </Card>
  )
}
