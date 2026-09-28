import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card } from './ui.jsx'
import { festivalsNear, listFestivals } from '../lib/festivalService.js'

const IMPACT_CLS = {
  low: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  medium: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  high: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
}

// Festival & Local Event Intelligence: local festivals near the tourist
// (this app's curated calendar) plus real national public holidays fetched
// live from the free Nager.Date public-holiday API (no key) -- a public
// holiday isn't tied to one coordinate, so it's fetched separately and
// merged in rather than filtered by distance. See backend/app/services/festival.py.
export default function FestivalCalendarCard({ lat, lng }) {
  const { t } = useTranslation()
  const [festivals, setFestivals] = useState([])
  const [holidays, setHolidays] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      festivalsNear(lat, lng, 200, 90),
      listFestivals({ category: 'public_holiday', within_days: 90 }),
    ])
      .then(([near, holiday]) => { setFestivals(near); setHolidays(holiday) })
      .catch(() => setError(t('festivals.failed')))
      .finally(() => setLoading(false))
  }, [lat, lng, t])

  return (
    <Card title={t('festivals.card_title')} icon="🎉" iconColor="bg-pink-50 text-pink-600 dark:bg-pink-900/30 dark:text-pink-300">
      <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">{t('festivals.intro')}</p>
      {loading && <div className="text-xs text-slate-400">{t('app.loading')}</div>}
      {error && <div className="text-sm text-red-600 dark:text-red-400">{error}</div>}
      {!loading && !error && festivals.length === 0 && holidays.length === 0 && (
        <div className="text-xs text-slate-400">{t('festivals.none_upcoming')}</div>
      )}

      {holidays.length > 0 && (
        <div className="mb-3">
          <div className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1.5">{t('festivals.public_holidays')}</div>
          <div className="flex flex-wrap gap-1.5">
            {holidays.map((h) => (
              <span key={h.id} title={h.description}
                className="text-xs font-medium bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 px-2.5 py-1 rounded-full">
                {h.name} · {h.next_start}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-2">
        {festivals.map((f) => (
          <div key={f.id} className="border border-slate-100 dark:border-slate-700 rounded-lg p-2.5 text-sm">
            <div className="flex items-center justify-between mb-1">
              <span className="font-medium">{f.name}</span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${IMPACT_CLS[f.crowd_impact]}`}>
                {t(`festivals.impact_${f.crowd_impact}`)}
              </span>
            </div>
            <div className="text-xs text-slate-500 dark:text-slate-400">{f.description}</div>
            <div className="text-xs text-slate-400 mt-1">
              {f.next_start} → {f.next_end}
              {f.distance_km != null && <> • {t('consular.km_away', { km: f.distance_km })}</>}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}
