import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import api from '../api'
import { relativeTime } from '../lib/relativeTime'
import { translateText } from '../lib/translationService'
import { speak, speechSynthesisSupported } from '../lib/voiceService'

const HAZARD_ICON = {
  flood: '🌊', landslide: '⛰️', earthquake: '🌍', storm: '⛈️',
  heavy_rain: '🌧️', thunderstorm: '🌩️', extreme_heat: '🔥',
  extreme_cold: '❄️', dense_fog: '🌫️', tsunami: '🌊', cyclone: '🌪️',
}
const SEVERITY_CLS = {
  critical: 'bg-red-600 text-white',
  high: 'bg-orange-500 text-white',
  medium: 'bg-yellow-500 text-white',
  low: 'bg-slate-400 text-white',
}

// A tourist's message is only spoken aloud once, and only for the more
// serious severities -- a module-level Set (not component state) so it
// survives this component unmounting/remounting as the tourist switches
// tabs, matching how notification dedup works on the backend side
// (Alert.disaster_advisory_id, see services/disaster.py).
const _spoken = new Set()

function AdvisoryMessage({ advisory, lang }) {
  const [translated, setTranslated] = useState(null)
  const [isDemo, setIsDemo] = useState(false)
  const { t } = useTranslation()

  useEffect(() => {
    if (lang === 'en') {
      setTranslated(null)
      return
    }
    let cancelled = false
    translateText(advisory.message, lang)
      .then((r) => {
        if (cancelled) return
        setTranslated(r.text)
        setIsDemo(!!r.demo)
      })
      .catch(() => { if (!cancelled) setTranslated(null) })
    return () => { cancelled = true }
  }, [advisory.message, lang])

  if (lang !== 'en' && translated === null) {
    return <div className="opacity-80">{t('disaster.translating')} {advisory.message}</div>
  }
  return (
    <div>
      {translated || advisory.message}
      {isDemo && <span className="ml-1 text-[10px] opacity-70">({t('translate.demo_label', 'demo')})</span>}
    </div>
  )
}

// Disaster & Weather Alert Feeds: any active hazard advisory for the zone
// the tourist is currently in. Polls GET /tourists/{id}/disasters -- see
// services/disaster.py. Every field rendered here (hazard type, severity,
// message, source, timestamps, instructions) comes straight from that real,
// database-backed advisory -- nothing here is a hardcoded alert.
export default function DisasterBanner({ touristId }) {
  const { t, i18n } = useTranslation()
  const [advisories, setAdvisories] = useState([])
  const prevIds = useRef(new Set())

  useEffect(() => {
    const load = () => api.get(`/tourists/${touristId}/disasters`).then((r) => setAdvisories(r.data)).catch(() => {})
    load()
    const iv = setInterval(load, 60000)
    return () => clearInterval(iv)
  }, [touristId])

  // Speak newly-seen high/critical advisories once, using the existing
  // browser TTS service (same one TranslateCard/the copilot use) -- never a
  // single hardcoded sentence, always generated from this advisory's own
  // hazard type, severity, zone message, and instructions.
  useEffect(() => {
    if (!speechSynthesisSupported()) return
    for (const a of advisories) {
      if (a.severity !== 'high' && a.severity !== 'critical') continue
      if (_spoken.has(a.id) || prevIds.current.has(a.id)) continue
      const spoken = [
        `Weather alert. A ${a.hazard_type.replace('_', ' ')} has been reported in your current area.`,
        a.message,
        a.instructions ? `Advice: ${a.instructions}` : null,
      ].filter(Boolean).join(' ')
      speak(spoken, i18n.language)
      _spoken.add(a.id)
    }
    prevIds.current = new Set(advisories.map((a) => a.id))
  }, [advisories, i18n.language])

  if (advisories.length === 0) return null

  return (
    <div className="space-y-2">
      {advisories.map((a) => (
        <div key={a.id} className={`rounded-xl p-3 text-sm font-medium space-y-1.5 ${SEVERITY_CLS[a.severity] || SEVERITY_CLS.medium}`}>
          <div className="flex items-start gap-2">
            <span className="text-lg leading-none">{HAZARD_ICON[a.hazard_type] || '⚠️'}</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-bold uppercase text-xs tracking-wide">
                  {a.title || t('disaster.advisory', { type: a.hazard_type })}
                </span>
                <span className="text-[10px] uppercase font-bold bg-black/20 rounded px-1.5 py-0.5">
                  {t('disaster.severity', { level: a.severity })}
                </span>
              </div>
              <AdvisoryMessage advisory={a} lang={i18n.language} />
              {a.instructions && (
                <div className="text-xs mt-1 opacity-90">
                  <span className="font-semibold">{t('disaster.instructions')}: </span>
                  {a.instructions}
                </div>
              )}
              <div className="text-[10px] mt-1.5 opacity-80 flex flex-wrap gap-x-3 gap-y-0.5">
                {a.zone_name && <span>📍 {a.zone_name}</span>}
                <span>{t('disaster.source')}: {a.source}</span>
                {a.issued_at && <span>{t('disaster.updated')}: {relativeTime(a.issued_at)}</span>}
                {a.expires_at && <span>{t('disaster.expires')}: {new Date(a.expires_at).toLocaleTimeString()}</span>}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
