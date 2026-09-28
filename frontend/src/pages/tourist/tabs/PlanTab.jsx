import { useTranslation } from 'react-i18next'
import { Card } from '../../../components/ui.jsx'
import TabHero from '../../../components/TabHero.jsx'
import RiskForecastStrip from '../../../components/RiskForecastStrip.jsx'
import RoutePicker from '../../../components/RoutePicker.jsx'
import CheckInCard from '../../../components/CheckInCard.jsx'
import ItineraryUploadCard from '../../../components/ItineraryUploadCard.jsx'
import VoiceNavigationAssistant from '../../../components/VoiceNavigationAssistant.jsx'

// Everything about planning ahead: how risk changes over the next hour,
// picking a safer route, the itinerary, and check-in/out. The route-picker
// state itself is shared with HomeTab's map (see useTouristData.js) since
// destination-picking happens by tapping the map and only one tab is
// mounted at a time.
export default function PlanTab({ data }) {
  const { t, i18n } = useTranslation()
  const { me, riskForecast, tid, routePicker, routePickerOpen, setRoutePickerOpen, load } = data

  return (
    <div className="space-y-4">
      <TabHero icon="🧭" title={t('plan_hero.title')} subtitle={t('plan_hero.subtitle')}
        gradient="from-indigo-500 via-violet-500 to-purple-600" />

      <RiskForecastStrip forecast={riskForecast} />

      <VoiceNavigationAssistant touristId={tid} lang={i18n.resolvedLanguage || i18n.language} />

      <button onClick={() => setRoutePickerOpen((v) => !v)}
        className="w-full text-sm font-semibold text-white bg-gradient-to-r from-sky-500 to-indigo-500 hover:from-sky-600 hover:to-indigo-600 rounded-xl py-2.5 shadow-sm">
        {routePickerOpen ? t('plan.hide_route_planner') : t('plan.plan_safe_route')}
      </button>
      <RoutePicker active={routePickerOpen} onToggle={() => setRoutePickerOpen(false)} state={routePicker} />

      <ItineraryUploadCard touristId={tid} onConfirmed={load} />

      <Card title={t('itinerary.title')} icon="🗺️" iconColor="bg-indigo-50 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-300" actions={
        me.itinerary?.length > 0 && (
          <span className="text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/30 rounded-full px-2 py-0.5">
            🟢 {t('itinerary.route_safe')}
          </span>
        )
      }>
        {/* A connected vertical journey line, not just a bare list -- each
            stop is still exactly `me.itinerary[i]`, "next stop" is still
            i === 0, nothing about the underlying data changed. */}
        <ol className="relative">
          {me.itinerary?.map((w, i) => (
            <li key={i} className="relative flex items-start gap-3 pb-4 last:pb-0">
              {i < me.itinerary.length - 1 && (
                <span className="absolute left-[9px] top-6 bottom-0 w-px bg-gradient-to-b from-indigo-200 to-slate-200 dark:from-indigo-800 dark:to-slate-700" />
              )}
              <span className={`mt-0.5 w-5 h-5 rounded-full shrink-0 z-10 flex items-center justify-center text-[10px] font-bold ${
                i === 0
                  ? 'bg-indigo-500 text-white ring-4 ring-indigo-100 dark:ring-indigo-900/40'
                  : 'bg-slate-200 dark:bg-slate-600 text-slate-500 dark:text-slate-300'}`}>
                {i + 1}
              </span>
              <div className="text-sm">
                <span className={i === 0 ? 'font-semibold text-slate-900 dark:text-slate-100' : 'text-slate-500 dark:text-slate-400'}>{w.name}</span>
                {i === 0 && <span className="block text-xs text-indigo-600 dark:text-indigo-400 font-medium">📍 {t('itinerary.next_stop')}</span>}
              </div>
            </li>
          ))}
        </ol>
      </Card>

      <CheckInCard touristId={tid} />
    </div>
  )
}
