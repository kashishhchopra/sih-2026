import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card } from './ui.jsx'
import useOnlineStatus from '../hooks/useOnlineStatus.js'
import api from '../api.js'
import { getOfflineBundle } from '../lib/discoveryService.js'

// Offline Trip: one place that pulls together everything a tourist needs
// with weak/no connectivity -- itinerary, emergency contacts, nearest
// hospital/police + national emergency numbers (services/safety_card.py),
// and nearby Discovery places -- all plain GETs, so the PWA's Workbox
// NetworkFirst cache (frontend/vite.config.js's `api-get-cache` rule)
// already serves the last successful response with no network at all. This
// card's only job is to fetch that bundle and say plainly whether what's
// on screen is live or a saved copy -- never to hide the difference.
export default function OfflineTripCard({ touristId, me, lat, lng }) {
  const { t } = useTranslation()
  const online = useOnlineStatus()
  const [safetyCard, setSafetyCard] = useState(null)
  const [discovery, setDiscovery] = useState(null)
  const [fetchedAt, setFetchedAt] = useState(null)
  const [error, setError] = useState('')

  const load = () => {
    setError('')
    Promise.all([
      api.get(`/tourists/${touristId}/safety-card`).then((r) => r.data),
      getOfflineBundle(lat, lng, 25),
    ])
      .then(([card, bundle]) => {
        setSafetyCard(card)
        setDiscovery(bundle)
        setFetchedAt(new Date())
      })
      .catch(() => setError(t('offline_trip.failed')))
  }

  useEffect(load, [touristId, lat, lng]) // eslint-disable-line react-hooks/exhaustive-deps

  const contacts = me?.emergency_contacts || []

  return (
    <Card title={t('offline_trip.card_title')} icon="📥" iconColor="bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300"
      actions={
        <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${online
          ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
          : 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300'}`}>
          {online ? t('offline_trip.online_data') : t('offline_trip.offline_saved_data')}
        </span>
      }>
      <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">{t('offline_trip.intro')}</p>
      {error && <div className="text-sm text-red-600 dark:text-red-400 mb-2">{error}</div>}
      {fetchedAt && (
        <div className="text-[11px] text-slate-400 mb-3">
          {t('offline_trip.as_of', { time: fetchedAt.toLocaleString() })}
        </div>
      )}

      <div className="space-y-3 text-sm">
        <div>
          <div className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">{t('offline_trip.itinerary')}</div>
          {me?.itinerary?.length > 0 ? (
            <ol className="list-decimal list-inside text-slate-700 dark:text-slate-200">
              {me.itinerary.map((w, i) => <li key={i}>{w.name}</li>)}
            </ol>
          ) : (
            <div className="text-xs text-slate-400">{t('offline_trip.no_itinerary')}</div>
          )}
        </div>

        <div>
          <div className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">{t('offline_trip.emergency_contacts')}</div>
          {contacts.length > 0 ? (
            <ul className="text-slate-700 dark:text-slate-200 space-y-0.5">
              {contacts.map((c, i) => <li key={i}>{c.name} ({c.relation}) — {c.phone}</li>)}
            </ul>
          ) : (
            <div className="text-xs text-slate-400">{t('offline_trip.no_contacts')}</div>
          )}
        </div>

        {safetyCard && (
          <div>
            <div className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">{t('offline_trip.nearest_help')}</div>
            <div className="text-slate-700 dark:text-slate-200">
              {safetyCard.nearest_hospital && (
                <div>🏥 {safetyCard.nearest_hospital.name} — {safetyCard.nearest_hospital.distance_km} km</div>
              )}
              {safetyCard.nearest_police && (
                <div>🚓 {safetyCard.nearest_police.name} — {safetyCard.nearest_police.distance_km} km</div>
              )}
            </div>
          </div>
        )}

        {discovery?.places?.length > 0 && (
          <div>
            <div className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">{t('offline_trip.saved_places')}</div>
            <ul className="text-slate-700 dark:text-slate-200 space-y-0.5">
              {discovery.places.slice(0, 5).map((p) => <li key={p.id}>{p.name} — {p.distance_km} km</li>)}
            </ul>
          </div>
        )}
      </div>
    </Card>
  )
}
