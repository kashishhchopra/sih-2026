import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import api from '../api'
import { Card } from './ui.jsx'

// Embassy/consulate + country-specific guidance for a foreign tourist.
// Fetches the same /safety-card payload SafetyCardPanel does (already
// covered by the PWA's offline GET cache, see vite.config.js) rather than
// threading state through it -- renders nothing for an Indian national or
// an unrecognised nationality, since safety_card.py omits the `consular`
// key in both cases.
export default function ConsularCard({ touristId }) {
  const { t } = useTranslation()
  const [card, setCard] = useState(null)

  useEffect(() => {
    api.get(`/tourists/${touristId}/safety-card`).then((r) => setCard(r.data)).catch(() => {})
  }, [touristId])

  if (!card || !card.consular) return null
  const { consular, country_guidance: guidance } = card

  return (
    <Card title={t('consular.card_title')}>
      <div className="space-y-3 text-sm">
        <div>
          <div className="font-medium text-slate-900 dark:text-slate-100">
            {consular.country_name} {consular.mission_type}
          </div>
          <div className="text-xs text-slate-500 dark:text-slate-400">{consular.city}</div>
          {consular.distance_km != null && (
            <div className="text-xs text-slate-500 dark:text-slate-400">{t('consular.km_away', { km: consular.distance_km })}</div>
          )}
          <a href={`tel:${consular.phone}`}
            className="inline-block mt-1 text-sky-600 dark:text-sky-400 font-semibold">
            ☎ {consular.phone}
          </a>
        </div>

        {guidance && (
          <details className="text-xs text-slate-500 dark:text-slate-400">
            <summary className="cursor-pointer font-medium text-slate-700 dark:text-slate-300">
              {t('consular.guidance_for', { lang: guidance.helpline_language })}
            </summary>
            <div className="mt-2 space-y-2">
              <p>{guidance.visa_overstay_note}</p>
              {guidance.common_scams?.length > 0 && (
                <div>
                  <div className="font-semibold text-slate-600 dark:text-slate-300">{t('consular.common_scams')}</div>
                  <ul className="list-disc list-inside">
                    {guidance.common_scams.map((s) => <li key={s}>{s}</li>)}
                  </ul>
                </div>
              )}
              {guidance.police_reporting_steps?.length > 0 && (
                <div>
                  <div className="font-semibold text-slate-600 dark:text-slate-300">{t('consular.reporting_steps')}</div>
                  <ul className="list-disc list-inside">
                    {guidance.police_reporting_steps.map((s) => <li key={s}>{s}</li>)}
                  </ul>
                </div>
              )}
            </div>
          </details>
        )}
      </div>
    </Card>
  )
}
