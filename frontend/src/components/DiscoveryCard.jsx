import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card } from './ui.jsx'
import useOnlineStatus from '../hooks/useOnlineStatus.js'
import { getDiscovery } from '../lib/discoveryService.js'

const CATEGORY_ICON = { hidden_gem: '💎', regional_food: '🍲', homestay: '🏡' }
const CATEGORIES = ['hidden_gem', 'regional_food', 'homestay']

// Discovery: hidden spots, regional food, and homestays near the tourist --
// live from OpenStreetMap where available, database-backed otherwise (see
// backend/app/services/discovery.py). Offline behaviour follows the same
// pattern as SafetyCardPanel: this is a plain GET, so the PWA's Workbox
// cache (frontend/vite.config.js) already serves the last good response
// with no signal -- the badge below only reports *that* it's doing so.
export default function DiscoveryCard({ lat, lng }) {
  const { t } = useTranslation()
  const online = useOnlineStatus()
  const [places, setPlaces] = useState([])
  const [category, setCategory] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    setError('')
    getDiscovery(lat, lng, 30, category ? [category] : null)
      .then((r) => setPlaces(r.places))
      .catch(() => setError(t('discovery.failed')))
      .finally(() => setLoading(false))
  }, [lat, lng, category, t])

  return (
    <Card title={t('discovery.card_title')} icon="🧭" iconColor="bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-300"
      actions={
        !online && (
          <span className="text-[11px] font-semibold bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300 px-2 py-0.5 rounded-full">
            {t('safety_card.offline_copy')}
          </span>
        )
      }>
      <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">{t('discovery.intro')}</p>
      {error && <div className="text-sm text-red-600 dark:text-red-400 mb-2">{error}</div>}
      {loading && <div className="text-xs text-slate-400 mb-2">{t('app.loading')}</div>}

      <div className="flex flex-wrap gap-1.5 mb-3">
        <button onClick={() => setCategory(null)}
          className={`text-xs font-medium px-2.5 py-1.5 rounded-full ${!category ? 'bg-emerald-600 text-white' : 'bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200'}`}>
          {t('discovery.all')}
        </button>
        {CATEGORIES.map((c) => (
          <button key={c} onClick={() => setCategory(c)}
            className={`text-xs font-medium px-2.5 py-1.5 rounded-full ${category === c ? 'bg-emerald-600 text-white' : 'bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200'}`}>
            {CATEGORY_ICON[c]} {t(`discovery.category_${c}`)}
          </button>
        ))}
      </div>

      <div className="space-y-2 max-h-72 overflow-y-auto">
        {!loading && places.length === 0 && <div className="text-xs text-slate-400">{t('discovery.none_found')}</div>}
        {places.map((p) => (
          <div key={p.id} className="border border-slate-100 dark:border-slate-700 rounded-lg p-2.5 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-medium">{CATEGORY_ICON[p.category]} {p.name}</span>
              <span className="text-xs text-slate-400">{t('consular.km_away', { km: p.distance_km })}</span>
            </div>
            {p.tip && <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{p.tip}</div>}
            <div className="text-[10px] text-slate-400 mt-1">
              {p.source === 'osm' ? t('discovery.source_osm') : t('discovery.source_curated')}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}
