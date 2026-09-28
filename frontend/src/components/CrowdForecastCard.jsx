import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card } from './ui.jsx'
import { getCrowdForecast } from '../lib/crowdForecastService.js'

const DENSITY_CLS = {
  low: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  medium: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  high: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
}

// Crowd & Queue Forecast: per-zone crowd forecast combining live density,
// peak/off-peak season, holiday windows, active festivals and weather. See
// backend/app/services/crowd_forecast.py.
export default function CrowdForecastCard() {
  const { t } = useTranslation()
  const [forecast, setForecast] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getCrowdForecast()
      .then(setForecast)
      .catch(() => setError(t('crowd_forecast.failed')))
      .finally(() => setLoading(false))
  }, [t])

  return (
    <Card title={t('crowd_forecast.card_title')} icon="👥" iconColor="bg-orange-50 text-orange-600 dark:bg-orange-900/30 dark:text-orange-300">
      <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">{t('crowd_forecast.intro')}</p>
      {loading && <div className="text-xs text-slate-400">{t('app.loading')}</div>}
      {error && <div className="text-sm text-red-600 dark:text-red-400">{error}</div>}
      <div className="space-y-2">
        {forecast.map((z) => (
          <div key={z.zone_id} className="border border-slate-100 dark:border-slate-700 rounded-lg p-2.5 text-sm">
            <div className="flex items-center justify-between mb-1">
              <span className="font-medium">{z.zone}</span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${DENSITY_CLS[z.forecast_density]}`}>
                {t(`crowd_forecast.density_${z.forecast_density}`)}
              </span>
            </div>
            <div className="text-xs text-slate-400">
              {t('crowd_forecast.reasons', { list: z.reasons.join(' • ') })}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}
