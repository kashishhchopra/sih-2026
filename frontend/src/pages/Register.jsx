import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api from '../api'
import { useAuth } from '../auth.jsx'
import { COUNTRIES } from '../lib/countries.js'
import LivenessCapture from '../components/LivenessCapture.jsx'
import PasswordChecklist from '../components/PasswordChecklist.jsx'
import {
  DOCUMENT_ERRORS, documentFieldStatus, documentMaxLength,
  filterDocumentNumberInput, filterNameInput, filterPhoneInput,
  NAME_ERROR, nameFieldStatus, normalizeDocumentNumber, normalizeName,
  PHONE_ERROR, phoneFieldStatus, validateDocumentNumber, validateName, validatePhone,
} from '../lib/identityValidation.js'
import { validatePassword } from '../lib/passwordValidation.js'

const DOC_TYPES = [
  { value: '', label: 'Select Verification Method' },
  { value: 'aadhaar', label: 'Aadhaar' },
  { value: 'passport', label: 'Passport' },
  { value: 'voterid', label: 'Voter ID' },
  { value: 'pan', label: 'PAN' },
]

const VISA_TYPES = ['e-Visa', 'Tourist', 'Business', 'Medical', 'Conference']

// Step list is built per-registration rather than a fixed array: a
// passport-type registration (foreign tourist) needs a "Visa & Travel" step
// the domestic-document flow doesn't. Keyed by a stable id (not index) so
// validators/render logic can't drift out of sync when the array's shape
// changes based on document_type -- see useMemo below.
function buildSteps(documentType) {
  const steps = [
    { key: 'identity', label: 'Identity' },
    { key: 'document', label: 'Document' },
  ]
  if (documentType === 'passport') {
    steps.push({ key: 'visa', label: 'Visa & Travel' })
  }
  steps.push(
    { key: 'photo', label: 'Photo' },
    { key: 'trip', label: 'Trip' },
    { key: 'emergency', label: 'Emergency Contact' },
    { key: 'account', label: 'Account' },
  )
  return steps
}

// Downscales+recompresses so a phone-camera photo doesn't bloat the request
// (stored as a data: URI column -- see backend/app/models/tourist.py).
function _resizePhoto(dataUrl, maxSize = 480) {
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => {
      const scale = Math.min(1, maxSize / Math.max(img.width, img.height))
      const canvas = document.createElement('canvas')
      canvas.width = img.width * scale
      canvas.height = img.height * scale
      canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height)
      resolve(canvas.toDataURL('image/jpeg', 0.85))
    }
    img.onerror = () => resolve(dataUrl)
    img.src = dataUrl
  })
}

function GlobeShell({ children }) {
  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{ background: '#04070d' }}>
      <style>{`
        .reg-globe { position: relative; width: 260px; height: 260px; border-radius: 50%;
          background: radial-gradient(circle at 32% 28%, #4fd1ff 0%, #0ea5e9 28%, #075985 55%, #03203a 78%, #01111f 100%);
          box-shadow: 0 0 70px rgba(14,165,233,0.4), inset -24px -16px 50px rgba(0,0,0,0.55);
        }
        .reg-globe::before { content:''; position:absolute; inset:0; opacity:.5;
          background-image:
            radial-gradient(circle at 20% 40%, rgba(255,255,255,0.18) 0 3%, transparent 4%),
            radial-gradient(circle at 60% 20%, rgba(255,255,255,0.14) 0 5%, transparent 6%),
            radial-gradient(circle at 75% 65%, rgba(255,255,255,0.16) 0 4%, transparent 5%);
        }
        .reg-input { background: transparent; border: 1px solid rgba(148,163,184,0.4); color: #e6f1ff; }
        .reg-input::placeholder { color: rgba(230,241,255,0.4); }
        .reg-input:focus { outline: none; border-color: #22d3ee; }
        .reg-input option { color: #0f172a; }
      `}</style>
      <div className="w-full max-w-4xl grid grid-cols-1 md:grid-cols-2 gap-10 items-center">
        <div className="hidden md:flex justify-center">
          <div className="reg-globe"></div>
        </div>
        <div className="text-white">{children}</div>
      </div>
    </div>
  )
}

function StepDots({ steps, activeKey }) {
  const activeIndex = steps.findIndex((s) => s.key === activeKey)
  return (
    <div className="flex items-center gap-2 mb-6">
      {steps.map((s, i) => (
        <div key={s.key} className={`h-1.5 flex-1 rounded-full ${i <= activeIndex ? 'bg-cyan-400' : 'bg-white/15'}`} title={s.label}></div>
      ))}
    </div>
  )
}

// Real-time validation feedback for an identity/contact field. Never relies
// on color alone (§14): an invalid/incomplete state always carries text too.
// "incomplete" (still typing, not long enough yet) is shown as a neutral
// hint rather than a red error -- only a genuinely wrong, complete-length
// value or a value the user has moved past (touched) shows as an error.
function FieldHint({ status, touched }) {
  if (!status || status.state === 'empty' || status.state === 'valid') {
    return status?.state === 'valid'
      ? <p className="text-xs text-emerald-400 mt-1">✓ Looks good</p>
      : null
  }
  if (status.state === 'incomplete' && !touched) {
    return <p className="text-xs text-slate-400 mt-1">{status.message}</p>
  }
  return <p className="text-xs text-red-300 mt-1">❌ {status.message}</p>
}

// Live camera capture -- no file upload, matching the Digital Tourist Safety
// ID's photo requirement (a real-time capture, not an arbitrary picture).
function LivePhotoCapture({ photo, onCapture, onRetake }) {
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const [error, setError] = useState('')
  const [ready, setReady] = useState(false)

  const stop = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
  }

  useEffect(() => {
    if (photo) return undefined
    let cancelled = false
    setError('')
    setReady(false)
    navigator.mediaDevices?.getUserMedia({ video: { facingMode: 'user' } })
      .then((stream) => {
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return }
        streamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          videoRef.current.play()
          setReady(true)
        }
      })
      .catch(() => setError('Camera access is required to capture your Digital ID photo. Please allow camera access and retry.'))
    return () => { cancelled = true; stop() }
  }, [photo])

  const capture = async () => {
    const video = videoRef.current
    if (!video) return
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    canvas.getContext('2d').drawImage(video, 0, 0)
    const dataUrl = canvas.toDataURL('image/jpeg', 0.9)
    stop()
    onCapture(await _resizePhoto(dataUrl))
  }

  if (photo) {
    return (
      <div className="flex items-center gap-4">
        <img src={photo} alt="Captured" className="w-28 h-28 rounded-xl object-cover border border-white/20" />
        <button type="button" onClick={onRetake}
          className="text-xs font-semibold bg-white/10 hover:bg-white/20 border border-white/20 px-3 py-2 rounded-lg">
          Retake photo
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="relative w-full max-w-xs mx-auto rounded-xl overflow-hidden bg-black" style={{ aspectRatio: '1/1' }}>
        <video ref={videoRef} muted playsInline className="w-full h-full object-cover -scale-x-100" />
      </div>
      {error && <div className="text-xs text-red-300 text-center">{error}</div>}
      <button type="button" onClick={capture} disabled={!ready}
        className="w-full bg-gradient-to-r from-cyan-400 to-sky-500 text-slate-900 font-bold py-2 rounded-lg disabled:opacity-50">
        📸 Capture Photo
      </button>
    </div>
  )
}

export default function Register() {
  const { login } = useAuth()
  const nav = useNavigate()
  const [f, setF] = useState({
    full_name: '', nationality: 'Indian', document_type: '',
    document_number: '', phone: '', email: '', password: '',
    trip_start: '', trip_end: '', hotel: '', photo: null, liveness_token: null,
    nationality_code: '', visa_type: '', visa_number: '', visa_expiry: '', passport_expiry: '',
  })
  // Whether the 3-step liveness check ran for this attempt -- turned off
  // permanently for the rest of this registration the moment it can't run
  // (camera denied, model unavailable, or the tourist opts out), falling
  // back to the existing plain live-capture step below. Never re-enabled
  // mid-registration: retrying a half-failed camera pipeline silently is
  // more likely to strand the tourist than to help them.
  const [livenessAvailable, setLivenessAvailable] = useState(true)
  const steps = useMemo(() => buildSteps(f.document_type), [f.document_type])
  const [stepKey, setStepKey] = useState('identity')
  const [contact, setContact] = useState({ name: '', phone: '', relation: 'family' })
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  // Smart Identity & Contact Validation: which identity/contact fields the
  // user has moved on from (blurred) -- gates whether an incomplete value
  // shows as a neutral hint or a hard error (see FieldHint above).
  const [touched, setTouched] = useState({})
  const touch = (k) => () => setTouched((prev) => ({ ...prev, [k]: true }))

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  // Real-time input restriction (Level 1, §9): filters every keystroke (and
  // paste) through the same shape rules the backend validates against, so
  // an unsupported character is rejected as it's typed rather than flagged
  // afterwards. Level 2 (the authoritative check) is the backend's own
  // TouristCreate validators -- see backend/app/core/identity_validators.py.
  // A silently-dropped keystroke is invisible ("I pressed @ and nothing
  // happened") -- rejected tracks whether the just-typed character got
  // filtered out, so the UI can say so instead of staying quiet.
  const [rejected, setRejected] = useState({ full_name: false, phone: false, document_number: false })
  const setName = (e) => {
    const filtered = filterNameInput(e.target.value)
    setF({ ...f, full_name: filtered })
    setRejected((r) => ({ ...r, full_name: filtered.length < e.target.value.length }))
  }
  const setPhone = (e) => {
    const filtered = filterPhoneInput(e.target.value)
    setF({ ...f, phone: filtered })
    setRejected((r) => ({ ...r, phone: filtered.length < e.target.value.length }))
  }
  const setDocumentNumber = (e) => {
    const filtered = filterDocumentNumberInput(f.document_type, e.target.value)
    setF({ ...f, document_number: filtered })
    setRejected((r) => ({ ...r, document_number: filtered.length < e.target.value.length }))
  }

  const nameStatus = nameFieldStatus(f.full_name)
  const phoneStatus = phoneFieldStatus(f.phone)
  const documentStatus = documentFieldStatus(f.document_type, f.document_number)

  const validators = {
    identity: () => validateName(f.full_name) && f.document_type,
    document: () => validatePhone(f.phone) && validateDocumentNumber(f.document_type, f.document_number),
    visa: () => f.nationality_code && f.visa_type && f.visa_expiry,
    photo: () => !!f.photo, // live camera capture is mandatory for the Digital ID card
    trip: () => f.trip_start && f.trip_end && new Date(f.trip_end) > new Date(f.trip_start),
    emergency: () => true, // optional
    // Credentials are optional (see the account step's own hint), but if
    // either field is started, both are required and the password must
    // meet the same strength rule the backend enforces (see
    // lib/passwordValidation.js / backend/app/core/security.py).
    account: () => (!f.email && !f.password) || (!!f.email && validatePassword(f.password)),
  }
  const stepIndex = steps.findIndex((s) => s.key === stepKey)
  const canAdvance = validators[stepKey]()

  const next = () => {
    if (!canAdvance) {
      setError('Please fill in the required fields to continue.')
      return
    }
    setError('')
    const nextIndex = Math.min(stepIndex + 1, steps.length - 1)
    setStepKey(steps[nextIndex].key)
  }
  const back = () => {
    setError('')
    const prevIndex = Math.max(stepIndex - 1, 0)
    setStepKey(steps[prevIndex].key)
  }

  const submit = async (e) => {
    e.preventDefault()
    if (!canAdvance) {
      setError('Please provide a valid password (see the checklist above) or leave both fields empty.')
      return
    }
    setError('')
    setLoading(true)
    try {
      const payload = {
        full_name: normalizeName(f.full_name),
        nationality: f.document_type === 'passport'
          ? (COUNTRIES.find((c) => c.code === f.nationality_code)?.name || f.nationality_code)
          : f.nationality,
        document_type: f.document_type,
        document_number: normalizeDocumentNumber(f.document_type, f.document_number),
        phone: f.phone,
        photo: f.photo || null,
        liveness_token: f.liveness_token || null,
        hotel: f.hotel || null,
        email: f.email || null,
        password: f.password || null,
        trip_start: new Date(f.trip_start).toISOString(),
        trip_end: new Date(f.trip_end).toISOString(),
        emergency_contacts: contact.name && contact.phone ? [contact] : [],
        itinerary: [],
      }
      if (f.document_type === 'passport') {
        payload.visa_type = f.visa_type
        payload.visa_number = f.visa_number || null
        payload.visa_expiry = f.visa_expiry ? new Date(f.visa_expiry).toISOString() : null
        payload.passport_expiry = f.passport_expiry ? new Date(f.passport_expiry).toISOString() : null
      }
      const { data } = await api.post('/tourists', payload)
      setResult(data)
      if (f.email && f.password) {
        setTimeout(async () => {
          const u = await login(f.email, f.password)
          nav(u.role === 'admin' ? '/admin' : '/app')
        }, 1600)
      }
    } catch (err) {
      const d = err.response?.data?.detail
      setError(typeof d === 'string' ? d : (Array.isArray(d) ? d.map((x) => x.msg).join('; ') : 'Registration failed'))
    } finally {
      setLoading(false)
    }
  }

  if (result) {
    return (
      <GlobeShell>
        <div className="bg-white/5 border border-white/10 rounded-2xl p-8 text-center backdrop-blur-sm">
          <div className="text-5xl mb-3">✅</div>
          <h1 className="text-xl font-bold">Your Unique Blockchain ID</h1>
          <div className="mt-3 text-2xl font-mono font-bold text-cyan-300 tracking-wider">{result.digital_id}</div>
          <p className="text-sm text-slate-300 mt-3">
            Anchored as the genesis block of your tamper-evident ID chain.
            Valid until {new Date(result.trip_end).toLocaleDateString()}.
          </p>
          <p className="text-sm text-slate-400 mt-1">{f.email ? 'Signing you in…' : ''}</p>
          {!f.email && (
            <Link to="/login" className="inline-block mt-5 bg-gradient-to-r from-cyan-400 to-sky-500 text-slate-900 font-bold px-6 py-2.5 rounded-xl">
              Continue to Login
            </Link>
          )}
        </div>
      </GlobeShell>
    )
  }

  const label = 'text-sm font-medium text-slate-300'
  const input = `reg-input mt-1 w-full rounded-lg px-3 py-2.5`
  const activeLabel = steps[stepIndex]?.label

  return (
    <GlobeShell>
      <div className="bg-white/5 border border-white/10 rounded-2xl p-8 backdrop-blur-sm">
        <div className="flex items-center justify-between mb-1">
          <h1 className="text-2xl font-bold">Identity Verification</h1>
          <Link to="/login" className="text-xs text-slate-400 hover:text-slate-200">Back to login</Link>
        </div>
        <p className="text-xs text-slate-400 mb-5">Step {stepIndex + 1} of {steps.length} — {activeLabel}</p>
        <StepDots steps={steps} activeKey={stepKey} />

        <form onSubmit={stepKey === 'account' ? submit : (e) => { e.preventDefault(); next() }} className="space-y-4">
          {stepKey === 'identity' && (
            <>
              <label className={label}>Enter Full Name
                <input className={input} value={f.full_name} onChange={setName} onBlur={touch('full_name')}
                  placeholder="Enter Full Name" required minLength={2} maxLength={120} /></label>
              {rejected.full_name
                ? <p className="text-xs text-red-300 mt-1">❌ {NAME_ERROR}</p>
                : <FieldHint status={nameStatus} touched={touched.full_name} />}
              <label className={label}>Select Verification Method
                <select className={input} value={f.document_type}
                  onChange={(e) => setF({ ...f, document_type: e.target.value, document_number: '' })} required>
                  {DOC_TYPES.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                </select></label>
            </>
          )}

          {stepKey === 'document' && (
            <>
              <label className={label}>{f.document_type ? DOC_TYPES.find((d) => d.value === f.document_type)?.label : 'Document'} Number
                <input className={input} value={f.document_number} onChange={setDocumentNumber} onBlur={touch('document_number')}
                  placeholder={DOCUMENT_ERRORS[f.document_type] ? `e.g. ${{ aadhaar: '123456789012', passport: 'A1234567', voterid: 'ABC1234567', pan: 'ABCDE1234F' }[f.document_type]}` : 'Enter document number'}
                  required minLength={4} maxLength={documentMaxLength(f.document_type)} /></label>
              {rejected.document_number && DOCUMENT_ERRORS[f.document_type]
                ? <p className="text-xs text-red-300 mt-1">❌ {DOCUMENT_ERRORS[f.document_type]}</p>
                : <FieldHint status={documentStatus} touched={touched.document_number} />}
              <label className={label}>Phone
                <input className={input} value={f.phone} onChange={setPhone} onBlur={touch('phone')}
                  placeholder="9876543210" inputMode="numeric" required maxLength={10} /></label>
              {rejected.phone
                ? <p className="text-xs text-red-300 mt-1">❌ {PHONE_ERROR}</p>
                : <FieldHint status={phoneStatus} touched={touched.phone} />}
              {f.document_type === 'passport' ? (
                <label className={label}>Country of Citizenship
                  <select className={input} value={f.nationality_code} onChange={set('nationality_code')} required>
                    <option value="">Select country</option>
                    {COUNTRIES.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
                  </select></label>
              ) : (
                <label className={label}>Nationality
                  <input className={input} value={f.nationality} onChange={set('nationality')} /></label>
              )}
            </>
          )}

          {stepKey === 'visa' && (
            <>
              <p className="text-xs text-slate-400 -mt-1 mb-2">Required for passport-based registration.</p>
              <label className={label}>Visa Type
                <select className={input} value={f.visa_type} onChange={set('visa_type')} required>
                  <option value="">Select visa type</option>
                  {VISA_TYPES.map((v) => <option key={v} value={v}>{v}</option>)}
                </select></label>
              <label className={label}>Visa Number (optional)
                <input className={input} value={f.visa_number} onChange={set('visa_number')}
                  placeholder="Visa number" /></label>
              <label className={label}>Visa Expiry
                <input type="date" className={input} value={f.visa_expiry} onChange={set('visa_expiry')} required /></label>
              <label className={label}>Passport Expiry (optional)
                <input type="date" className={input} value={f.passport_expiry} onChange={set('passport_expiry')} /></label>
              <p className="text-xs text-slate-400">Your visa must be valid through your entire planned trip.</p>
            </>
          )}

          {stepKey === 'photo' && (
            <>
              {!f.photo && livenessAvailable ? (
                <>
                  <p className="text-xs text-slate-400 -mt-1 mb-2">
                    Your camera will be used briefly to verify that a real person is present and to
                    capture your Digital Tourist Safety ID photo.
                  </p>
                  <LivenessCapture
                    onCapture={(photo, meta) => setF((prev) => ({ ...prev, photo, liveness_token: meta?.livenessToken || null }))}
                    onCancel={() => setLivenessAvailable(false)}
                    onUnavailable={() => setLivenessAvailable(false)}
                  />
                </>
              ) : (
                <>
                  <p className="text-xs text-slate-400 -mt-1 mb-2">
                    Required — a live camera capture for your Digital Tourist Safety ID card (no file uploads, to
                    make sure the photo is really of you, right now).
                    {!livenessAvailable && !f.photo && (
                      <span className="block mt-1 text-orange-300">
                        Step-by-step verification isn't available in this browser — using standard live capture instead.
                      </span>
                    )}
                  </p>
                  <LivePhotoCapture photo={f.photo}
                    onCapture={(photo) => setF((prev) => ({ ...prev, photo, liveness_token: null }))}
                    onRetake={() => setF((prev) => ({ ...prev, photo: null }))} />
                </>
              )}
            </>
          )}

          {stepKey === 'trip' && (
            <>
              <label className={label}>Trip Start
                <input type="datetime-local" className={input} value={f.trip_start} onChange={set('trip_start')} required /></label>
              <label className={label}>Trip End
                <input type="datetime-local" className={input} value={f.trip_end} onChange={set('trip_end')} required /></label>
              <label className={label}>Hotel / Accommodation
                <input className={input} value={f.hotel} onChange={set('hotel')} placeholder="e.g. ABC Residency" /></label>
              <p className="text-xs text-slate-400">Your digital ID stays valid for exactly this window.</p>
            </>
          )}

          {stepKey === 'emergency' && (
            <>
              <p className="text-xs text-slate-400 -mt-1 mb-2">Optional, but strongly recommended — notified automatically on SOS.</p>
              <label className={label}>Contact name
                <input className={input} value={contact.name}
                  onChange={(e) => setContact({ ...contact, name: e.target.value })} placeholder="Name" /></label>
              <label className={label}>Contact phone
                <input className={input} value={contact.phone}
                  onChange={(e) => setContact({ ...contact, phone: e.target.value })} placeholder="Phone" /></label>
              <label className={label}>Relation
                <input className={input} value={contact.relation}
                  onChange={(e) => setContact({ ...contact, relation: e.target.value })} placeholder="family" /></label>
            </>
          )}

          {stepKey === 'account' && (
            <>
              <p className="text-xs text-slate-400 -mt-1 mb-2">Optional — set credentials to access the tourist app after registering.</p>
              <label className={label}>Email
                <input type="email" className={input} value={f.email} onChange={set('email')} placeholder="you@example.com" /></label>
              <label className={label}>Password
                <input type="password" className={input} value={f.password} onChange={set('password')} /></label>
              {f.password && <PasswordChecklist password={f.password} />}
            </>
          )}

          {error && <div className="text-sm text-red-300 bg-red-500/10 border border-red-500/30 rounded-lg p-2">{error}</div>}

          <div className="flex items-center gap-3 pt-2">
            {stepIndex > 0 && (
              <button type="button" onClick={back}
                className="flex-1 border border-white/20 text-slate-200 font-semibold py-2.5 rounded-lg">
                Back
              </button>
            )}
            <button type="submit" disabled={loading || (stepKey === 'account' && !canAdvance)}
              className="flex-[2] bg-gradient-to-r from-cyan-400 to-sky-500 text-slate-900 font-bold py-2.5 rounded-lg disabled:opacity-60">
              {stepKey === 'account'
                ? (loading ? 'Issuing…' : 'Get Your Unique Blockchain ID')
                : 'Next'}
            </button>
          </div>
        </form>
      </div>
    </GlobeShell>
  )
}
