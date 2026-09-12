import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import BottomSheet from '../../../components/BottomSheet.jsx'
import useSpeechRecognition from '../../../hooks/useSpeechRecognition'

// Optional context typed/spoken before an SOS is sent. Deliberately NOT on
// the critical path -- the footer SOS button fires immediately regardless
// of whether this sheet was ever opened; this only lets a tourist add detail
// first if they have a moment to.
export default function ReportSheet({ open, onClose, data, lang }) {
  const { t } = useTranslation()
  const { emergencyMessage, setEmergencyMessage, sendSOS, sosSent, sosQueued, pendingCount } = data
  const speech = useSpeechRecognition({ lang })

  // Voice input fills the description box as soon as a transcript arrives --
  // the tourist can review or edit it before sending.
  useEffect(() => {
    if (speech.transcript) setEmergencyMessage(speech.transcript)
  }, [speech.transcript, setEmergencyMessage])

  const handleSend = async () => {
    await sendSOS()
    speech.reset()
  }

  return (
    <BottomSheet open={open} onClose={onClose} title={t('sos.describe_title')}>
      <textarea
        value={emergencyMessage}
        onChange={(e) => setEmergencyMessage(e.target.value)}
        placeholder={t('sos.describe_placeholder')}
        rows={4}
        className="w-full border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 rounded-lg px-3 py-2 text-sm resize-none"
      />
      <div className="flex items-center justify-between mt-2">
        {speech.supported ? (
          <button
            onClick={speech.listening ? speech.stop : speech.start}
            className={`text-xs font-semibold px-3 py-1.5 rounded-lg flex items-center gap-1.5 ${
              speech.listening ? 'bg-red-100 text-red-700' : 'bg-slate-100 text-slate-700'}`}>
            {speech.listening ? t('sos.listening') : t('sos.speak')}
          </button>
        ) : (
          <span className="text-xs text-slate-400">{t('sos.voice_unsupported')}</span>
        )}
        {speech.error && <span className="text-xs text-red-500">{speech.error}</span>}
      </div>
      <div className="text-xs text-slate-400 mt-2">{t('sos.describe_note')}</div>

      <button onClick={handleSend}
        className="w-full mt-4 bg-red-600 hover:bg-red-700 text-white font-bold py-3 rounded-xl">
        🆘 {t('sos.button')}
      </button>

      {sosSent && (
        <div className="bg-red-600 text-white rounded-xl p-4 text-sm mt-4">
          <div className="font-bold">🚨 {t('sos.sent_title')}</div>
          {sosSent.nearest_unit && (
            <div className="mt-1">
              {t('sos.dispatched', {
                name: sosSent.nearest_unit.name,
                station: sosSent.nearest_unit.station,
                km: sosSent.nearest_unit.distance_km,
              })}
            </div>
          )}
          <div className="mt-1 text-red-100 text-xs">
            {t('sos.contacts_notified', {
              list: sosSent.notified_contacts?.map((c) => c.name).join(', '),
            })}
          </div>
        </div>
      )}

      {sosQueued && (
        <div className="bg-orange-500 text-white rounded-xl p-4 text-sm mt-4">
          <div className="font-bold">{t('sos.queued_title')}</div>
          <div className="mt-1 text-orange-50">
            {t('sos.queued_body')}
          </div>
        </div>
      )}

      {pendingCount > 0 && !sosQueued && (
        <div className="text-xs text-center text-orange-600 dark:text-orange-400 mt-2">
          {t('sos.pending_count', { count: pendingCount })}
        </div>
      )}
    </BottomSheet>
  )
}
