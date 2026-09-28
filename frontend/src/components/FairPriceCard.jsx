import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card } from './ui.jsx'
import { geocodePlace } from '../lib/mapsService.js'
import {
  listTransportTypes, createFareCheck, listFareChecks, reportFare,
} from '../lib/fareService.js'

const TRANSPORT_ICON = { auto_rickshaw: '🛺', taxi: '🚕', cab: '🚗', bike_taxi: '🏍️' }
const VERDICT_CLS = {
  fair: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  slightly_high: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  overpriced: 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
  suspicious: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
}

// Fair Price: is the fare a local driver just quoted reasonable? Real route
// distance/duration (services/maps.py) x a transparent, configurable rate
// card (services/fare.py) -- never a single hardcoded price. Pickup
// defaults to the tourist's current live location; destination is a place
// name the tourist types, geocoded on submit.
export default function FairPriceCard({ touristId, lat, lng }) {
  const { t } = useTranslation()
  const [types, setTypes] = useState([])
  const [transportType, setTransportType] = useState('auto_rickshaw')
  const [destinationName, setDestinationName] = useState('')
  const [quotedFare, setQuotedFare] = useState('')
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState('')
  const [checks, setChecks] = useState([])
  const [reportingId, setReportingId] = useState(null)

  const load = () => {
    listTransportTypes().then(setTypes).catch(() => {})
    listFareChecks(touristId).then(setChecks).catch(() => {})
  }
  useEffect(load, [touristId]) // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async (e) => {
    e.preventDefault()
    if (!destinationName.trim() || !quotedFare) return
    setChecking(true)
    setError('')
    try {
      const dest = await geocodePlace(destinationName.trim())
      if (dest.lat == null) {
        setError(t('fair_price.destination_not_found'))
        return
      }
      await createFareCheck(touristId, {
        transport_type: transportType, pickup_name: t('fair_price.current_location'),
        pickup_lat: lat, pickup_lng: lng,
        destination_name: destinationName.trim(), destination_lat: dest.lat, destination_lng: dest.lng,
        quoted_fare: Number(quotedFare),
      })
      setDestinationName('')
      setQuotedFare('')
      load()
    } catch {
      setError(t('fair_price.check_failed'))
    } finally {
      setChecking(false)
    }
  }

  const doReport = async (checkId) => {
    setReportingId(checkId)
    try {
      await reportFare(touristId, checkId)
      load()
    } finally {
      setReportingId(null)
    }
  }

  return (
    <Card title={t('fair_price.card_title')} icon="💰" iconColor="bg-amber-50 text-amber-600 dark:bg-amber-900/30 dark:text-amber-300">
      <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">{t('fair_price.intro')}</p>

      <form onSubmit={submit} className="flex flex-col gap-2 mb-3">
        <select value={transportType} onChange={(e) => setTransportType(e.target.value)}
          className="text-sm border border-slate-200 dark:border-slate-600 dark:bg-slate-700 rounded-lg px-2 py-1.5">
          {types.map((tt) => (
            <option key={tt} value={tt}>{TRANSPORT_ICON[tt]} {t(`fair_price.transport_${tt}`, tt.replace(/_/g, ' '))}</option>
          ))}
        </select>
        <input value={destinationName} onChange={(e) => setDestinationName(e.target.value)}
          placeholder={t('fair_price.destination_placeholder')}
          className="text-sm border border-slate-200 dark:border-slate-600 dark:bg-slate-700 rounded-lg px-2 py-1.5" />
        <input type="number" min="1" step="1" value={quotedFare} onChange={(e) => setQuotedFare(e.target.value)}
          placeholder={t('fair_price.quoted_fare_placeholder')}
          className="text-sm border border-slate-200 dark:border-slate-600 dark:bg-slate-700 rounded-lg px-2 py-1.5" />
        {error && <div className="text-sm text-red-600 dark:text-red-400">{error}</div>}
        <button disabled={checking || !destinationName.trim() || !quotedFare}
          className="text-sm font-semibold bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white py-2 rounded-lg">
          {checking ? t('fair_price.checking') : t('fair_price.check_button')}
        </button>
      </form>

      <div className="space-y-2">
        {checks.length === 0 && <div className="text-xs text-slate-400">{t('fair_price.none_yet')}</div>}
        {checks.map((c) => (
          <div key={c.id} className="border border-slate-100 dark:border-slate-700 rounded-lg p-2.5 text-sm">
            <div className="flex items-center justify-between mb-1">
              <span className="font-medium">{TRANSPORT_ICON[c.transport_type]} {c.destination_name}</span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${VERDICT_CLS[c.verdict]}`}>
                {t(`fair_price.verdict_${c.verdict}`)}
              </span>
            </div>
            <div className="text-xs text-slate-500 dark:text-slate-400">
              {t('fair_price.estimated_range', { min: c.estimated_min, max: c.estimated_max })}
              {' · '}{t('fair_price.quoted', { amount: c.quoted_fare })}
              {c.percent_diff > 0 && ` · +${c.percent_diff}%`}
            </div>
            <div className="text-[11px] text-slate-400 mt-0.5">
              {c.distance_km} km · ~{Math.round(c.duration_min)} min
            </div>
            {c.verdict !== 'fair' && !c.reported && (
              <button onClick={() => doReport(c.id)} disabled={reportingId === c.id}
                className="mt-2 text-xs font-semibold bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 px-3 py-1.5 rounded-lg disabled:opacity-50">
                {reportingId === c.id ? t('fair_price.reporting') : t('fair_price.report_button')}
              </button>
            )}
            {c.reported && (
              <div className="mt-2 text-[11px] text-red-500 font-semibold">{t('fair_price.reported_notice')}</div>
            )}
          </div>
        ))}
      </div>
    </Card>
  )
}
