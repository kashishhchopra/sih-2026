import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import api from '../api'
import { Card } from './ui.jsx'
import useOnlineStatus from '../hooks/useOnlineStatus'

// Offline Maps & Safety Card: nearest hospital/police + emergency numbers.
// This works with no signal because the browser's service worker already
// caches this GET response (see vite.config.js's api-get-cache rule) --
// nothing offline-specific needs to happen here beyond fetching normally.
export default function SafetyCardPanel({ touristId }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [card, setCard] = useState(null)
  const online = useOnlineStatus()

  useEffect(() => {
    if (!open || card) return
    api.get(`/tourists/${touristId}/safety-card`).then((r) => setCard(r.data)).catch(() => {})
  }, [open, touristId])

  return (
    <div>
      <button onClick={() => setOpen((v) => !v)}
        className="w-full text-sm font-semibold text-sky-700 dark:text-sky-400 bg-sky-50 dark:bg-sky-900/30 rounded-xl py-2">
        {open ? t('safety_card.toggle_hide') : t('safety_card.toggle_show')}
      </button>

      {open && (
        <div className="mt-3">
          {!card && <div className="text-sm text-slate-400 text-center py-4">{t('safety_card.loading')}</div>}
          {card && (
            <Card title={t('safety_card.card_title')} actions={
              !online && <span className="text-xs bg-orange-100 text-orange-700 px-2 py-0.5 rounded-full font-semibold">{t('safety_card.offline_copy')}</span>
            }>
              <div className="space-y-3 text-sm">
                <div>
                  <div className="text-xs text-slate-500 dark:text-slate-400 mb-1">{t('safety_card.nearest_hospital')}</div>
                  {card.nearest_hospital ? (
                    <div>{card.nearest_hospital.name} — {card.nearest_hospital.distance_km} km — ☎ {card.nearest_hospital.phone}</div>
                  ) : <div className="text-slate-400">{t('safety_card.not_available')}</div>}
                </div>
                <div>
                  <div className="text-xs text-slate-500 dark:text-slate-400 mb-1">{t('safety_card.nearest_police')}</div>
                  {card.nearest_police ? (
                    <div>{card.nearest_police.name} — {card.nearest_police.distance_km} km — ☎ {card.nearest_police.phone}</div>
                  ) : <div className="text-slate-400">{t('safety_card.not_available')}</div>}
                </div>
                <div>
                  <div className="text-xs text-slate-500 dark:text-slate-400 mb-1">{t('safety_card.emergency_numbers')}</div>
                  <div className="grid grid-cols-2 gap-1.5">
                    {Object.entries(card.emergency_numbers).map(([k, v]) => (
                      <div key={k} className="flex justify-between bg-slate-50 dark:bg-slate-900 rounded-lg px-2 py-1">
                        <span className="capitalize text-slate-500 dark:text-slate-400">{k.replace(/_/g, ' ')}</span>
                        <span className="font-bold">{v}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="text-[11px] text-slate-400 pt-1">{card.note}</div>
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
