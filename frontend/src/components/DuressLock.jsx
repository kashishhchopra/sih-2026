import { useState } from 'react'
import api from '../api'
import { Card } from './ui.jsx'

// Silent / Duress SOS.
//
// Two pieces, deliberately separate:
//  - DuressPinSettings: setting the PIN is an explicit, clearly-labeled
//    action in the tourist's own safety settings.
//  - DuressLockButton: the *trigger* is disguised as an ordinary "app lock"
//    passcode pad. Whether the PIN entered is correct or wrong, the screen
//    always shows the same bland "Incorrect passcode" -- so someone watching
//    over the tourist's shoulder cannot tell a silent SOS was just sent.
export function DuressPinSettings({ touristId }) {
  const [pin, setPin] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const save = async (e) => {
    e.preventDefault()
    if (!/^\d{4,8}$/.test(pin)) return
    setSaving(true)
    try {
      await api.post(`/tourists/${touristId}/duress-pin`, { pin })
      setPin('')
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card title="Silent / Duress SOS">
      <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">
        Set a duress PIN. If you're ever forced to prove your phone is
        "locked," entering this PIN on the lock pad below sends a silent SOS
        with your location — the screen shows nothing unusual.
      </p>
      <form onSubmit={save} className="flex items-center gap-2">
        <input value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
          inputMode="numeric" maxLength={8} placeholder="4-8 digit PIN"
          className="flex-1 border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 rounded-lg px-3 py-2 text-sm tracking-widest" />
        <button disabled={saving || !/^\d{4,8}$/.test(pin)}
          className="bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white text-sm font-semibold px-4 py-2 rounded-lg">
          {saving ? 'Saving…' : 'Set PIN'}
        </button>
      </form>
      {saved && <div className="text-xs text-green-600 mt-2">Duress PIN saved.</div>}
    </Card>
  )
}

export function DuressLockButton({ touristId, getPosition, className = 'text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300' }) {
  const [open, setOpen] = useState(false)
  const [entry, setEntry] = useState('')
  const [msg, setMsg] = useState('')

  const press = (d) => setEntry((e) => (e.length < 8 ? e + d : e))
  const backspace = () => setEntry((e) => e.slice(0, -1))

  const submit = async () => {
    const [lat, lng] = getPosition() || [null, null]
    // Fire-and-forget-looking: identical bland outcome regardless of whether
    // the PIN matched, so there is nothing on screen to give it away.
    try {
      if (lat != null) {
        await api.post(`/tourists/${touristId}/sos/duress`, { pin: entry, lat, lng, message: 'Duress PIN triggered' })
      }
    } catch {
      // A wrong PIN 400s here -- same visible outcome as a correct one.
    }
    setEntry('')
    setMsg('Incorrect passcode. Try again.')
    setTimeout(() => setMsg(''), 2000)
  }

  return (
    <>
      <button onClick={() => setOpen(true)} className={className} title="App lock">
        🔒
      </button>
      {open && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[2000] p-4">
          <div className="bg-white dark:bg-slate-800 rounded-2xl p-6 w-full max-w-xs text-center">
            <div className="text-sm text-slate-500 dark:text-slate-400 mb-3">Enter passcode to unlock</div>
            <div className="text-2xl tracking-[0.5em] mb-3 h-8">{'•'.repeat(entry.length)}</div>
            {msg && <div className="text-xs text-red-500 mb-2">{msg}</div>}
            <div className="grid grid-cols-3 gap-2">
              {['1', '2', '3', '4', '5', '6', '7', '8', '9', '⌫', '0', '✓'].map((k) => (
                <button key={k}
                  onClick={() => k === '⌫' ? backspace() : k === '✓' ? submit() : press(k)}
                  className="bg-slate-100 dark:bg-slate-700 rounded-lg py-3 text-lg font-medium">
                  {k}
                </button>
              ))}
            </div>
            <button onClick={() => { setOpen(false); setEntry(''); setMsg('') }}
              className="mt-4 text-xs text-slate-400">Cancel</button>
          </div>
        </div>
      )}
    </>
  )
}
