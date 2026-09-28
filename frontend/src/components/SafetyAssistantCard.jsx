import { useTranslation } from 'react-i18next'

// Illustrated promo card for the voice/AI assistant -- same visual language
// as a travel app's "Find a travel buddy" card, but every button reuses a
// handler HomeTab already has (voice assistant, route planner, nearby
// hospital/police/transport), so nothing here is a new feature -- just a
// friendlier front door to features that already exist elsewhere.
const ACTIONS = [
  { key: 'voice', icon: '🎤', labelKey: 'home_extra.assistant_ask' },
  { key: 'route', icon: '🗺️', labelKey: 'home_extra.assistant_route' },
  { key: 'hospital', icon: '🏥', labelKey: 'home_extra.assistant_hospital' },
  { key: 'police', icon: '👮', labelKey: 'home_extra.assistant_police' },
  { key: 'transport', icon: '🚕', labelKey: 'home_extra.assistant_transport' },
]

export default function SafetyAssistantCard({ onVoice, onNavigateTab, setRoutePickerOpen }) {
  const { t } = useTranslation()
  const go = (key) => {
    switch (key) {
      case 'voice': onVoice(); break
      case 'route': setRoutePickerOpen(true); onNavigateTab('plan'); break
      case 'hospital': case 'police': case 'transport': onNavigateTab('help'); break
      default: break
    }
  }

  return (
    <div className="rounded-[var(--theme-radius)] p-4 shadow-[var(--theme-shadow)] text-white
                    bg-gradient-to-br from-sky-500 to-sky-700 relative overflow-hidden">
      {/* A single decorative shape, not a second 🤖 glyph -- the real floating
          chat button elsewhere in the app already owns that emoji as its
          accessible label, and a duplicate would make it ambiguous. */}
      <div className="absolute -right-6 -top-6 w-24 h-24 rounded-full bg-white/10 pointer-events-none" />
      <div className="relative">
        <div className="font-bold">{t('home_extra.assistant_title')}</div>
        <div className="text-sm text-sky-50 mt-0.5">{t('home_extra.assistant_subtitle')}</div>
        <div className="flex flex-wrap gap-1.5 mt-3">
          {ACTIONS.map((a) => (
            <button key={a.key} onClick={() => go(a.key)}
              className="text-xs font-semibold bg-white/15 hover:bg-white/25 backdrop-blur rounded-full px-3 py-1.5">
              {a.icon} {t(a.labelKey)}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
