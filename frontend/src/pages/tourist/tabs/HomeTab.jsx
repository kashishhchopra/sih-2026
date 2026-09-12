import { useRef } from 'react'
import { MapContainer, TileLayer, Marker, Polygon } from 'react-leaflet'
import { useTranslation } from 'react-i18next'
import { DEFAULT_MAP } from '../../../config'
import { ScoreGauge, bandLabel } from '../../../components/ui.jsx'
import { touristIcon, policeIcon, riskColor } from '../../../components/mapIcons'
import ScoreExplanation from '../../../components/ScoreExplanation.jsx'
import TrajectoryOverlay from '../../../components/TrajectoryOverlay.jsx'
import { RouteLayer } from '../../../components/RoutePicker.jsx'
import DisasterBanner from '../../../components/DisasterBanner.jsx'
import RecommendedPlaces from '../../../components/RecommendedPlaces.jsx'
import SafetyAssistantCard from '../../../components/SafetyAssistantCard.jsx'

// Quick-action row: the handful of things a tourist reaches for constantly,
// one tap away from the home screen, without cluttering it with full panels
// -- each button either opens the relevant tool in place (voice assistant)
// or jumps to the tab that has it (Plan/Help), so nothing here duplicates
// functionality that already lives elsewhere. SOS is deliberately NOT in
// this grid -- it has its own single circular button at the top of the
// screen instead (see SOSButton below); having it in two places on the
// same screen was confusing, not reassuring.
const QUICK_ACTIONS = [
  { key: 'voice', icon: '🎙️', labelKey: 'home.quick_voice' },
  { key: 'nav', icon: '🗺️', labelKey: 'home.quick_navigate' },
  { key: 'hospital', icon: '🏥', labelKey: 'home.quick_hospital' },
  { key: 'pharmacy', icon: '💊', labelKey: 'home.quick_pharmacy' },
  { key: 'transport', icon: '🚕', labelKey: 'home.quick_transport' },
  { key: 'translate', icon: '🌐', labelKey: 'home.quick_translate' },
  { key: 'itinerary', icon: '📄', labelKey: 'home.quick_itinerary' },
]

function QuickActions({ onVoice, onNavigateTab, setRoutePickerOpen }) {
  const { t } = useTranslation()
  const go = (key) => {
    switch (key) {
      case 'voice': onVoice(); break
      case 'nav': setRoutePickerOpen(true); onNavigateTab('plan'); break
      case 'hospital': case 'pharmacy': case 'transport': case 'translate':
        onNavigateTab('help'); break
      case 'itinerary': onNavigateTab('plan'); break
      default: break
    }
  }
  return (
    <div className="grid grid-cols-4 gap-2">
      {QUICK_ACTIONS.map((a) => (
        <button key={a.key} onClick={() => go(a.key)}
          className="flex flex-col items-center gap-1 rounded-2xl py-2.5 text-xs font-medium bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 shadow-sm">
          <span className="text-lg leading-none">{a.icon}</span>
          {t(a.labelKey)}
        </button>
      ))}
    </div>
  )
}

// The one SOS button for this screen: circular, top of the page, big enough
// to hit without looking -- not a full-width card. The word "SOS" is spelled
// out in bold rather than relying on an emoji glyph, so it reads clearly at
// any size and in any font. Calls the exact same sendSOS() as everywhere else.
function SOSButton({ onSOS }) {
  const { t } = useTranslation()
  return (
    <button onClick={onSOS} aria-label={t('sos.aria_label')}
      className="shrink-0 w-16 h-16 rounded-full flex items-center justify-center text-white
                bg-gradient-to-br from-red-600 to-rose-600 shadow-lg ring-4 ring-red-200 dark:ring-red-900/50 sos-pulse">
      <span className="text-base font-extrabold tracking-wide leading-none">SOS</span>
    </button>
  )
}

function greetingKey() {
  const h = new Date().getHours()
  if (h < 12) return 'home.greeting_morning'
  if (h < 17) return 'home.greeting_afternoon'
  return 'home.greeting_evening'
}

// The calm default screen: map, safety score, and the geofence/disaster
// state a tourist needs at a glance -- everything else moved to its own tab.
export default function HomeTab({ data, onVoice, onNavigateTab }) {
  const { t } = useTranslation()
  const { me, score, zones, trajectory, nearby, riskyZone, routePicker, routePickerOpen,
    setRoutePickerOpen, tid, sendSOS } = data
  const mapRef = useRef(null)
  const firstName = (me.full_name || '').split(' ')[0]

  return (
    <div className="space-y-4">
      {/* ---- Greeting + Safety Status hero -- "travel app first, safety
          system second": this is the first thing a tourist sees, and it
          reads like a trip companion checking in, not a monitoring panel. ---- */}
      <div>
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="text-lg font-bold text-slate-900 dark:text-slate-100">
              {t(greetingKey())}, {firstName || t('home.greeting_fallback')} 👋
            </div>
            <div className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1 mt-0.5">
              📍 {score.breakdown.zone}
            </div>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <div className="flex flex-col items-center gap-1">
              <ScoreGauge score={score.score} size={56} showLabel={false} />
              <span className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 whitespace-nowrap leading-none">
                {bandLabel(score.score)}
              </span>
            </div>
            <SOSButton onSOS={sendSOS} />
          </div>
        </div>

        <div className={`travel-accent mt-3 rounded-[var(--theme-radius)] p-4 shadow-[var(--theme-shadow)] ${
          riskyZone
            ? 'bg-amber-50 dark:bg-amber-900/25 border border-amber-200 dark:border-amber-800'
            : 'bg-white dark:bg-slate-800'}`}>
          <div className="flex items-center gap-2">
            <span className="text-2xl leading-none">{riskyZone ? '🟡' : '🟢'}</span>
            <div>
              <div className={`font-bold ${riskyZone ? 'text-amber-700 dark:text-amber-300' : 'text-emerald-600 dark:text-emerald-400'}`}>
                {riskyZone ? t('home.caution_title') : t('home.safe_title')}
              </div>
              <div className="text-xs text-slate-500 dark:text-slate-400">
                {riskyZone
                  ? t('home.caution_body', { zone: riskyZone.name })
                  : t('home.safe_body')}
              </div>
            </div>
          </div>
          <button onClick={() => mapRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })}
            className="mt-3 w-full text-sm font-semibold text-sky-700 dark:text-sky-300 bg-sky-50 dark:bg-sky-900/30 rounded-xl py-2">
            {t('home.view_live_map')}
          </button>
          <ScoreExplanation explanation={score.breakdown.explanation} />
        </div>
      </div>

      <QuickActions onVoice={onVoice} onNavigateTab={onNavigateTab}
        setRoutePickerOpen={setRoutePickerOpen} />

      <DisasterBanner touristId={tid} />

      {riskyZone ? (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <div className="font-semibold text-red-700">⚠ {t('geofence.warning_title')}</div>
          <div className="text-sm text-red-600 mt-1">
            {t('geofence.warning_body', { zone: riskyZone.name, risk: riskyZone.risk_level })}
          </div>
        </div>
      ) : (
        <div className="bg-green-50 border border-green-200 rounded-xl p-3 text-sm text-green-700">
          ✅ {t('geofence.safe')}
        </div>
      )}

      {routePickerOpen && (
        <div className="bg-sky-50 dark:bg-sky-900/30 border border-sky-200 dark:border-sky-800 rounded-xl p-3 text-xs text-sky-700 dark:text-sky-300">
          {t('home.route_picker_hint')}
        </div>
      )}

      {/* ---- Safety tip -- yellow, small, one at a time. Purely
          informational, rotates with the tourist's digital-id number so it
          feels alive without needing a real content feed. ---- */}
      <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-100 dark:border-amber-900/40 rounded-2xl p-3 flex items-start gap-2">
        <span className="text-lg leading-none">☀️</span>
        <div className="text-sm text-amber-800 dark:text-amber-300">
          <span className="font-semibold">{t('home.safety_tip_label')} </span>
          {t('home.safety_tip_body')}
        </div>
      </div>

      <RecommendedPlaces />

      <div ref={mapRef} className="bg-white dark:bg-slate-800 rounded-[var(--theme-radius)] shadow-[var(--theme-shadow)] overflow-hidden" style={{ height: 320 }}>
        <MapContainer
          center={me.last_lat != null && me.last_lng != null ? [me.last_lat, me.last_lng] : DEFAULT_MAP.center}
          zoom={14} style={{ height: '100%' }} key={me.id}>
          <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OSM" />
          {zones.map((z) => (
            <Polygon key={z.id} positions={z.polygon}
              pathOptions={{ color: riskColor[z.risk_level], fillOpacity: 0.15, weight: 1.5 }} />
          ))}
          {/* A brand-new tourist has no location yet -- before their first
              GPS/simulated ping lands, there's nothing real to place a
              marker at, so it's simply omitted rather than plotted at a
              null-coerced (0, 0) point. */}
          {me.last_lat != null && me.last_lng != null && (
            <Marker position={[me.last_lat, me.last_lng]} icon={touristIcon(score.score)} />
          )}
          {nearby.filter((u) => u.lat != null && u.lng != null)
            .map((u) => <Marker key={u.id} position={[u.lat, u.lng]} icon={policeIcon} />)}
          <TrajectoryOverlay points={trajectory} />
          <RouteLayer active={routePickerOpen} dest={routePicker.dest}
            result={routePicker.result} onPick={routePicker.pick} />
        </MapContainer>
      </div>

      <SafetyAssistantCard onVoice={onVoice} onNavigateTab={onNavigateTab} setRoutePickerOpen={setRoutePickerOpen} />
    </div>
  )
}
