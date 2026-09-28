import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { findNearby } from '../lib/mapsService.js'
import { Card } from './ui.jsx'

const CATEGORIES = [
  { key: 'hospital', labelKey: 'nearby.cat_hospital', icon: '🏥' },
  { key: 'pharmacy', labelKey: 'nearby.cat_pharmacy', icon: '💊' },
  { key: 'police', labelKey: 'nearby.cat_police', icon: '👮' },
  { key: 'transport', labelKey: 'nearby.cat_transport', icon: '🚕' },
]

// Nearby Transport / Healthcare discovery: real hospital/police data (the
// committed OSM import, see backend/services/poi.py); pharmacy/transport
// are seeded demo fixtures unless a live feed is added -- either way, every
// result is a real DB row with a real distance, never a fabricated
// "3 taxis available now" claim. "Get Directions" opens a real turn-by-turn
// maps deep link (no API key needed); calling uses a plain tel: link.
export default function NearbyPlacesCard({ touristId }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [category, setCategory] = useState('hospital')
  const [places, setPlaces] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const load = (cat) => {
    setCategory(cat)
    setLoading(true)
    setError('')
    findNearby(touristId, cat)
      .then(setPlaces)
      .catch(() => setError(t('nearby.load_error')))
      .finally(() => setLoading(false))
  }

  const toggle = () => {
    const next = !open
    setOpen(next)
    if (next && places === null) load(category)
  }

  return (
    <div>
      <button onClick={toggle}
        className="w-full text-sm font-semibold text-sky-700 dark:text-sky-400 bg-sky-50 dark:bg-sky-900/30 rounded-xl py-2">
        {open ? t('nearby.toggle_hide') : t('nearby.toggle_show')}
      </button>

      {open && (
        <div className="mt-3">
          <Card title={t('nearby.card_title')}>
            <div className="flex gap-1.5 mb-3 overflow-x-auto">
              {CATEGORIES.map((c) => (
                <button key={c.key} onClick={() => load(c.key)}
                  className={`text-xs font-semibold px-3 py-1.5 rounded-full whitespace-nowrap ${
                    category === c.key
                      ? 'bg-sky-600 text-white'
                      : 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300'}`}>
                  {c.icon} {t(c.labelKey)}
                </button>
              ))}
            </div>

            {loading && <div className="text-sm text-slate-400 text-center py-3">{t('nearby.loading')}</div>}
            {error && <div className="text-sm text-red-600 dark:text-red-400">{error}</div>}
            {!loading && !error && places && places.length === 0 && (
              <div className="text-sm text-slate-400 text-center py-3">
                {t('nearby.empty')}
              </div>
            )}
            {!loading && places && places.length > 0 && (
              <div className="space-y-2">
                {places.map((p, i) => (
                  <div key={i} className="flex items-center justify-between text-sm border-b border-slate-50 dark:border-slate-700/50 pb-2 last:border-0 last:pb-0">
                    <div className="min-w-0">
                      <div className="font-medium text-slate-800 dark:text-slate-100 truncate">{p.name}</div>
                      <div className="text-xs text-slate-400">
                        {t('nearby.km_away', { km: p.distance_km })}
                        {p.source === 'osm' && <span className="ml-1 text-green-600 dark:text-green-400">· {t('nearby.verified')}</span>}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {p.phone && (
                        <a href={`tel:${p.phone}`} className="text-lg" title={t('nearby.call_title', { phone: p.phone })}>📞</a>
                      )}
                      <a href={p.directions_url} target="_blank" rel="noreferrer"
                        className="text-xs bg-sky-600 hover:bg-sky-700 text-white font-semibold px-2.5 py-1.5 rounded-lg">
                        {t('nearby.directions')}
                      </a>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  )
}
