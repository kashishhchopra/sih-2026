import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../../auth.jsx'
import TabHero from '../../../components/TabHero.jsx'
import SafetyPassportCard from '../../../components/SafetyPassportCard.jsx'
import DigitalIdCard from '../../../components/DigitalIdCard.jsx'
import TripGuardianCard from '../../../components/TripGuardianCard.jsx'
import PrivacyCard from '../../../components/PrivacyCard.jsx'
import { DuressPinSettings } from '../../../components/DuressLock.jsx'
import LanguageSwitcher from '../../../components/LanguageSwitcher.jsx'
import ThemeToggle from '../../../components/ThemeToggle.jsx'

// Identity, sharing, and settings -- everything that isn't a moment-to-
// moment safety concern lives here so Home/Plan/Help stay uncluttered.
export default function MeTab({ data }) {
  const { t } = useTranslation()
  const { logout } = useAuth()
  const nav = useNavigate()
  const { tid, tracking, toggleTracking, geo } = data

  return (
    <div className="space-y-4">
      <TabHero icon="👤" title={t('me_hero.title')} subtitle={t('me_hero.subtitle')}
        gradient="from-fuchsia-500 via-purple-500 to-violet-600" />

      <DigitalIdCard touristId={tid} />
      <SafetyPassportCard touristId={tid} />

      <div className="bg-white dark:bg-slate-800 rounded-[var(--theme-radius)] shadow-[var(--theme-shadow)] p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <span className="w-9 h-9 rounded-full bg-purple-50 dark:bg-purple-900/30 flex items-center justify-center text-base shrink-0">📍</span>
            <div className="min-w-0">
              <div className="font-medium text-slate-900 dark:text-slate-100">{t('tracking.title')}</div>
              <div className="text-xs text-slate-500 dark:text-slate-400">{t('tracking.subtitle')}</div>
            </div>
          </div>
          <button onClick={toggleTracking}
            className={`w-14 h-8 rounded-full transition relative shrink-0 ${tracking ? 'bg-gradient-to-r from-emerald-400 to-green-500' : 'bg-slate-300 dark:bg-slate-600'}`}>
            <span className={`absolute top-1 w-6 h-6 bg-white rounded-full transition-all shadow ${tracking ? 'left-7' : 'left-1'}`}></span>
          </button>
        </div>
        {tracking && geo.permissionState === 'denied' && (
          <div className="mt-2 text-xs text-red-600">
            {t('me.location_permission_denied')}
          </div>
        )}
        {tracking && geo.permissionState === 'unsupported' && (
          <div className="mt-2 text-xs text-orange-600">
            {t('tracking.unsupported')}
          </div>
        )}
      </div>

      <TripGuardianCard touristId={tid} />
      <DuressPinSettings touristId={tid} />
      <PrivacyCard touristId={tid} />

      <div className="bg-white dark:bg-slate-800 rounded-[var(--theme-radius)] shadow-[var(--theme-shadow)] p-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span className="w-9 h-9 rounded-full bg-sky-50 dark:bg-sky-900/30 flex items-center justify-center text-base shrink-0">🌐</span>
          <div className="text-sm font-medium text-slate-900 dark:text-slate-100">{t('lang.label')}</div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <LanguageSwitcher />
          <ThemeToggle />
        </div>
      </div>

      <button onClick={() => { logout(); nav('/login') }}
        className="w-full text-sm font-semibold text-rose-600 dark:text-rose-400 border-2 border-rose-200 dark:border-rose-900/50 bg-rose-50/50 dark:bg-rose-900/10 hover:bg-rose-50 dark:hover:bg-rose-900/20 rounded-xl py-3">
        {t('app.logout')}
      </button>
    </div>
  )
}
