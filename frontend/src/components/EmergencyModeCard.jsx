import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import useEmergencyTracking from '../hooks/useEmergencyTracking'

const STATUS_META = {
  connecting: { labelKey: 'emergency_mode.status_connecting', dot: 'bg-slate-400', text: 'text-slate-300' },
  live: { labelKey: 'emergency_mode.status_live', dot: 'bg-emerald-400 animate-pulse', text: 'text-emerald-300' },
  stale: { labelKey: 'emergency_mode.status_stale', dot: 'bg-amber-400', text: 'text-amber-300' },
  offline: { labelKey: 'emergency_mode.status_offline', dot: 'bg-red-500', text: 'text-red-300' },
  stopped: { labelKey: 'emergency_mode.status_stopped', dot: 'bg-slate-500', text: 'text-slate-400' },
}

// The tourist's own "Emergency Mode" screen for an active SOS -- see
// backend/app/services/emergency_location.py for the real GPS -> backend ->
// police-dashboard pipeline this reflects. Deliberately never shown for a
// silent/duress SOS (sosSent.silent): a visible "Emergency Mode" banner on
// screen would defeat the entire point of a silent alert, even though the
// same real location sharing is still running underneath for police.
export default function EmergencyModeCard({ sosSent, tid, posRef }) {
  const { t } = useTranslation()
  const [confirmingCancel, setConfirmingCancel] = useState(false)
  const active = !!sosSent?.incident_id && !sosSent.silent
  const startPos = posRef?.current ? { lat: posRef.current[0], lng: posRef.current[1] } : null
  const tracking = useEmergencyTracking({
    tid, incidentId: sosSent?.incident_id, active, startPos,
  })

  if (!active) return null

  if (tracking.status === 'stopped') {
    return (
      <div className="fixed inset-x-4 bottom-40 z-[1400] max-w-sm mx-auto bg-slate-800 text-white rounded-2xl shadow-xl p-4 text-sm">
        <div className="font-bold">{t('emergency_mode.resolved_title')}</div>
        <div className="text-slate-300 mt-1">{t('emergency_mode.resolved_body')}</div>
      </div>
    )
  }

  const meta = STATUS_META[tracking.status] || STATUS_META.connecting

  return (
    <div className="fixed inset-x-4 bottom-40 z-[1400] max-w-sm mx-auto bg-red-700 text-white rounded-2xl shadow-2xl p-4 text-sm space-y-2.5">
      <div className="flex items-center justify-between">
        <div className="font-bold text-base">{t('emergency_mode.title')}</div>
        <span className={`flex items-center gap-1.5 text-xs font-bold ${meta.text}`}>
          <span className={`w-2 h-2 rounded-full ${meta.dot}`} /> {t(meta.labelKey)}
        </span>
      </div>

      <div className="text-red-50">
        {t('emergency_mode.sharing_notice')}
        {tracking.demo && <span className="block text-red-200 text-xs mt-0.5">{t('emergency_mode.demo_notice')}</span>}
      </div>

      {tracking.error && (
        <div className="bg-red-900/50 rounded-lg px-3 py-2 text-xs">
          {tracking.error === 'Connection interrupted' ? (
            <>{t('emergency_mode.connection_interrupted')}</>
          ) : (
            <>{t('emergency_mode.location_unavailable')}</>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <div className="text-red-200">{t('emergency_mode.police_station')}</div>
          <div className="font-semibold">{sosSent.station_name || t('emergency_mode.assigning')}</div>
        </div>
        <div>
          <div className="text-red-200">{t('emergency_mode.response')}</div>
          <div className="font-semibold">{sosSent.nearest_unit ? t('emergency_mode.officer_assigned') : t('emergency_mode.finding_responder')}</div>
        </div>
        <div>
          <div className="text-red-200">{t('emergency_mode.location_status')}</div>
          <div className="font-semibold">{t(meta.labelKey)}</div>
        </div>
        <div>
          <div className="text-red-200">{t('emergency_mode.last_updated')}</div>
          <div className="font-semibold">
            {tracking.secondsSinceUpdate == null ? '—' : t('emergency_mode.seconds_ago', { count: tracking.secondsSinceUpdate })}
          </div>
        </div>
      </div>

      <div className="flex gap-2 pt-1">
        <a href="tel:112" className="flex-1 text-center bg-white text-red-700 font-bold text-xs py-2 rounded-lg">
          {t('emergency_mode.call_emergency')}
        </a>
        <button
          onClick={() => (confirmingCancel ? tracking.stop() : setConfirmingCancel(true))}
          className="flex-1 bg-red-900/60 hover:bg-red-900 text-white font-semibold text-xs py-2 rounded-lg">
          {confirmingCancel ? t('emergency_mode.tap_again_confirm') : t('emergency_mode.cancel_emergency')}
        </button>
      </div>
      {confirmingCancel && (
        <button onClick={() => setConfirmingCancel(false)} className="w-full text-[11px] text-red-200 underline">
          {t('emergency_mode.keep_sharing')}
        </button>
      )}
    </div>
  )
}
