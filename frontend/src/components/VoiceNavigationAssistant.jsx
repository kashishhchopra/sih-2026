import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card } from './ui.jsx'
import { getNavigationGuidance } from '../lib/mapsService.js'
import { speak, stopSpeaking, speechSynthesisSupported } from '../lib/voiceService.js'

const POLL_MS = 15000
// Re-announce at most about once a minute, or immediately when the tourist
// crosses into a meaningfully different state (next stop, "close now",
// "arrived", or ~250m of real progress) -- a running commentary on every
// metre would be exhausting, not helpful.
const REMINDER_MS = 60000
const PROGRESS_BUCKET_M = 250

function progressKey(g) {
  if (!g.has_destination) return 'none'
  if (g.arrived) return `arrived:${g.destination_name}`
  const bucket = Math.floor(g.distance_m / PROGRESS_BUCKET_M)
  return `${g.destination_name}:${bucket}`
}

// Turn-by-turn-style voice guidance toward the tourist's next itinerary
// stop -- polls backend/services/navigation.py and speaks the instruction
// aloud, entirely opt-in via the on/off toggle (persisted per-tourist so
// the choice sticks across visits). Always shows the current instruction
// as text too, regardless of the toggle, so it's useful with sound off.
export default function VoiceNavigationAssistant({ touristId, lang = 'en' }) {
  const { t } = useTranslation()
  const storageKey = `voice-nav-enabled:${touristId}`
  const [enabled, setEnabled] = useState(() => {
    try {
      return localStorage.getItem(storageKey) === '1'
    } catch {
      return false
    }
  })
  const [guidance, setGuidance] = useState(null)
  const [error, setError] = useState('')
  const lastSpokenKeyRef = useRef(null)
  const lastSpokenAtRef = useRef(0)

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, enabled ? '1' : '0')
    } catch {
      // best-effort only -- a private/blocked storage just means the
      // preference won't stick across reloads, nothing breaks
    }
    if (!enabled) {
      stopSpeaking()
      lastSpokenKeyRef.current = null
    }
  }, [enabled, storageKey])

  useEffect(() => {
    let cancelled = false
    const tick = () => {
      getNavigationGuidance(touristId)
        .then((g) => {
          if (cancelled) return
          setGuidance(g)
          setError('')
          if (!enabled || !g.has_destination || !speechSynthesisSupported()) return
          const key = progressKey(g)
          const now = Date.now()
          const dueForReminder = now - lastSpokenAtRef.current > REMINDER_MS
          if (key !== lastSpokenKeyRef.current || dueForReminder) {
            lastSpokenKeyRef.current = key
            lastSpokenAtRef.current = now
            speak(g.instruction, lang)
          }
        })
        .catch(() => !cancelled && setError(t('voice_nav.guidance_unavailable')))
    }
    tick()
    const id = setInterval(tick, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [touristId, enabled, lang, t])

  return (
    <Card title={t('voice_nav.card_title')}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-slate-500 dark:text-slate-400">
          {t('voice_nav.subtitle')}
        </span>
        <button onClick={() => setEnabled((v) => !v)}
          aria-pressed={enabled}
          className={`text-xs font-semibold px-3 py-1.5 rounded-full whitespace-nowrap ${
            enabled ? 'bg-sky-600 text-white' : 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300'}`}>
          {enabled ? t('voice_nav.voice_on') : t('voice_nav.voice_off')}
        </button>
      </div>

      {error && <div className="text-xs text-red-600 dark:text-red-400">{error}</div>}

      {!error && guidance && !guidance.has_destination && (
        <div className="text-xs text-slate-400">
          {t('voice_nav.no_destination')}
        </div>
      )}

      {!error && guidance?.has_destination && (
        <div className="text-sm">
          <div className="font-medium text-slate-800 dark:text-slate-100">{guidance.instruction}</div>
          {!guidance.arrived && (
            <div className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              {t('voice_nav.eta', { km: guidance.distance_km, min: guidance.eta_minutes })}
              {guidance.demo && <span className="text-orange-500 dark:text-orange-400"> · {t('voice_nav.estimated')}</span>}
            </div>
          )}
        </div>
      )}

      {!speechSynthesisSupported() && (
        <div className="text-[10px] text-slate-400 mt-2">
          {t('voice_nav.no_speech_support')}
        </div>
      )}
    </Card>
  )
}
