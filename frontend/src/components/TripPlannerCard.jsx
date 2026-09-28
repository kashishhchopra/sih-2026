import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card } from './ui.jsx'
import { getTripPlan } from '../lib/tripPlannerService.js'

const BAND_CLS = {
  good: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  fair: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  poor: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
}

// Smart Trip Planner: turns the tourist's confirmed itinerary into a
// day-by-day plan, checking each day's stops against weather risk so a bad
// day can be re-planned before it happens. See backend/app/services/trip_planner.py.
export default function TripPlannerCard({ touristId }) {
  const { t } = useTranslation()
  const [plan, setPlan] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const generate = () => {
    setLoading(true)
    setError('')
    getTripPlan(touristId)
      .then(setPlan)
      .catch(() => setError(t('trip_planner.failed')))
      .finally(() => setLoading(false))
  }

  return (
    <Card title={t('trip_planner.card_title')} icon="🗓️" iconColor="bg-violet-50 text-violet-600 dark:bg-violet-900/30 dark:text-violet-300">
      <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">{t('trip_planner.intro')}</p>

      <button onClick={generate} disabled={loading}
        className="w-full text-sm font-semibold bg-violet-600 hover:bg-violet-700 disabled:opacity-50 text-white py-2 rounded-lg mb-3">
        {loading ? t('trip_planner.generating') : t('trip_planner.generate_button')}
      </button>

      {error && <div className="text-sm text-red-600 dark:text-red-400 mb-2">{error}</div>}

      {plan && plan.notes.length > 0 && (
        <div className="text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 rounded-lg p-2 mb-3 space-y-1">
          {plan.notes.map((n, i) => <div key={i}>⚠️ {n}</div>)}
        </div>
      )}

      {plan && plan.days.length > 0 && (
        <div className="space-y-2">
          {plan.days.map((day) => (
            <div key={day.day} className="border border-slate-100 dark:border-slate-700 rounded-lg p-2.5 text-sm">
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold">{t('trip_planner.day_label', { n: day.day, date: day.date })}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${BAND_CLS[day.weather_band]}`}>
                  {t(`trip_planner.weather_${day.weather_band}`)}
                </span>
              </div>
              <ul className="text-xs text-slate-500 dark:text-slate-400 list-disc list-inside">
                {day.stops.map((s, i) => <li key={i}>{s.name}</li>)}
              </ul>
              <div className="text-xs text-slate-400 mt-1">{day.advisory}</div>

              {day.festivals?.length > 0 && (
                <div className="mt-1.5 text-xs bg-pink-50 dark:bg-pink-900/20 text-pink-700 dark:text-pink-300 rounded-lg px-2 py-1">
                  🎉 {day.festivals.map((f) => f.name).join(', ')} {t('trip_planner.falls_on_this_day')}
                </div>
              )}
              {day.permits_suggested?.length > 0 && (
                <div className="mt-1.5 text-xs bg-indigo-50 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-300 rounded-lg px-2 py-1">
                  📝 {t('trip_planner.permit_may_be_needed', { types: day.permits_suggested.map((p) => p.replace(/_/g, ' ')).join(', ') })}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
