import { useTranslation } from 'react-i18next'

const TABS = [
  { key: 'home', icon: '🗺️', labelKey: 'nav.tab_home' },
  { key: 'plan', icon: '🧭', labelKey: 'nav.tab_plan' },
  { key: 'explore', icon: '🌍', labelKey: 'nav.tab_explore' },
  { key: 'help', icon: '🏥', labelKey: 'nav.tab_help' },
  { key: 'me', icon: '👤', labelKey: 'nav.tab_me' },
]

// Persistent bottom navigation for the tourist app. Kept separate from the
// SOS button (rendered by TouristShell above this) so the single most
// important action on the whole screen is never one of five equal-weight
// tab buttons.
export default function TouristTabBar({ active, onChange }) {
  const { t } = useTranslation()
  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-[1000] bg-white dark:bg-slate-800 border-t border-slate-200 dark:border-slate-700 pb-[env(safe-area-inset-bottom)]"
      aria-label={t('nav.sections_aria')}
    >
      <div className="max-w-md mx-auto grid grid-cols-5">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => onChange(tab.key)}
            aria-current={active === tab.key ? 'page' : undefined}
            className={`flex flex-col items-center justify-center gap-0.5 py-2 text-xs font-medium transition-colors ${
              active === tab.key
                ? 'text-sky-600 dark:text-sky-400'
                : 'text-slate-400 dark:text-slate-500'
            }`}
          >
            <span className="text-lg leading-none">{tab.icon}</span>
            {t(tab.labelKey)}
          </button>
        ))}
      </div>
    </nav>
  )
}

export { TABS }
