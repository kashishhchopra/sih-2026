import { useTranslation } from 'react-i18next'
import LanguageSwitcher from '../../components/LanguageSwitcher.jsx'
import ThemeToggle from '../../components/ThemeToggle.jsx'
import { DuressLockButton } from '../../components/DuressLock.jsx'

// Persistent chrome across every tab: digital ID + offline/duress controls
// up top, toast notifications, and the single SOS action at the bottom.
// Everything tab-specific is passed in as `children`.
export default function TouristShell({ digitalId, online, toast, onSOS, onReport, tid, posRef, children }) {
  const { t } = useTranslation()

  return (
    <div data-role-theme="tourist" className="theme-surface min-h-screen bg-slate-100 dark:bg-slate-900 pb-40">
      <div className="tourist-shell-header"
        style={{ background: 'linear-gradient(120deg, #0d4d47 0%, #0f766e 55%, #0e7c88 100%)', color: '#eafffb' }}>
        <div className="flex items-center justify-between px-5 py-4 max-w-md mx-auto">
          <div>
            <div className="text-xs opacity-70">{t('app.digital_id')}</div>
            <div className="font-bold tracking-wide">{digitalId}</div>
          </div>
          <div className="flex items-center gap-2">
            {!online && (
              <span className="text-xs bg-orange-500/90 px-2 py-1 rounded-full font-semibold">
                📡 {t('app.offline')}
              </span>
            )}
            <DuressLockButton touristId={tid} getPosition={() => posRef.current}
              className="text-xs text-slate-300 hover:text-white" />
            <LanguageSwitcher className="!border-slate-600 !text-slate-200 !bg-transparent" />
            <ThemeToggle className="!border-slate-600 !text-slate-200 !bg-transparent" />
          </div>
        </div>
      </div>

      {toast && (
        <div className="fixed top-16 left-1/2 -translate-x-1/2 bg-orange-500 text-white px-4 py-2 rounded-lg shadow-lg z-[1001] text-sm">
          {toast}
        </div>
      )}

      <div className="max-w-md mx-auto p-4">{children}</div>

      {/* SOS button -- always fires immediately; "Add details" opens the
          optional Report sheet without blocking the SOS tap. */}
      <div className="fixed bottom-14 left-0 right-0 p-4 bg-gradient-to-t from-slate-100 dark:from-slate-900 to-transparent pointer-events-none">
        <div className="max-w-md mx-auto space-y-2 pointer-events-auto">
          <button onClick={onSOS}
            className="w-full bg-red-600 hover:bg-red-700 text-white font-bold text-lg py-4 rounded-2xl shadow-lg sos-pulse">
            🆘 {t('sos.button')}
          </button>
          <button onClick={onReport}
            className="w-full text-xs font-medium text-slate-500 dark:text-slate-400 bg-white/80 dark:bg-slate-800/80 backdrop-blur rounded-lg py-1.5">
            {t('sos.add_details')}
          </button>
        </div>
      </div>
    </div>
  )
}
