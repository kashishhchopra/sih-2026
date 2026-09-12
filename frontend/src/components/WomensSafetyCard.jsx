import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card } from './ui.jsx'
import api from '../api.js'
import { previewSentiment, submitSafetyReport, listSafetyReports } from '../lib/sentimentService.js'

const URGENCY_CLS = {
  low: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  medium: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  high: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
}
const LABEL_ICON = { positive: '🙂', neutral: '😐', negative: '😟', fear: '😨', anger: '😠' }

// Women & Solo Traveller Safety: a real-time sentiment/distress check on a
// safety report before it's sent, backed by services/sentiment.py (VADER +
// a safety lexicon, never a hardcoded label) -- so the tourist sees exactly
// why a report reads as urgent, and a high-distress report automatically
// opens a real incident on the police side (services/monitoring.py:
// escalate_safety_report), on top of -- never instead of -- the SOS button.
export default function WomensSafetyCard({ touristId, posRef }) {
  const { t } = useTranslation()
  const [text, setText] = useState('')
  const [preview, setPreview] = useState(null)
  const [reports, setReports] = useState([])
  const [womenHelpline, setWomenHelpline] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const debounceRef = useRef(null)

  const load = () => {
    listSafetyReports(touristId).then(setReports).catch(() => {})
    // The women's helpline is real data already served by the existing
    // Offline Safety Card endpoint (services/safety_card.py) -- reused
    // here rather than a second, hardcoded copy of the same number.
    api.get(`/tourists/${touristId}/safety-card`)
      .then((r) => setWomenHelpline(r.data?.emergency_numbers?.women_helpline || ''))
      .catch(() => {})
  }
  useEffect(load, [touristId]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    clearTimeout(debounceRef.current)
    if (!text.trim()) { setPreview(null); return }
    debounceRef.current = setTimeout(() => {
      previewSentiment(text).then(setPreview).catch(() => {})
    }, 500)
    return () => clearTimeout(debounceRef.current)
  }, [text])

  const submit = async () => {
    if (!text.trim()) return
    setSubmitting(true)
    setError('')
    setResult(null)
    try {
      const [lat, lng] = posRef?.current || []
      const saved = await submitSafetyReport(touristId, text, lat, lng)
      setResult(saved)
      setText('')
      setPreview(null)
      load()
    } catch {
      setError(t('womens_safety.submit_failed'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Card title={t('womens_safety.card_title')} icon="🌸" iconColor="bg-fuchsia-50 text-fuchsia-600 dark:bg-fuchsia-900/30 dark:text-fuchsia-300">
      <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">{t('womens_safety.intro')}</p>

      {womenHelpline && (
        <a href={`tel:${womenHelpline}`}
          className="flex items-center justify-between text-sm bg-fuchsia-50 dark:bg-fuchsia-900/20 text-fuchsia-700 dark:text-fuchsia-300 rounded-lg px-3 py-2 mb-3 font-semibold">
          <span>{t('womens_safety.helpline_label')}</span>
          <span>☎ {womenHelpline}</span>
        </a>
      )}

      <textarea value={text} onChange={(e) => setText(e.target.value)}
        placeholder={t('womens_safety.textarea_placeholder')} rows={3}
        className="w-full text-sm border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 rounded-lg px-3 py-2 resize-none mb-2" />

      {preview && (
        <div className="flex items-center gap-2 mb-2 text-xs">
          <span className="font-medium text-slate-500 dark:text-slate-400">{LABEL_ICON[preview.label] || '💬'} {t(`womens_safety.sentiment_${preview.label}`, preview.label)}</span>
          <span className={`px-2 py-0.5 rounded-full font-semibold ${URGENCY_CLS[preview.urgency]}`}>
            {t('womens_safety.urgency_label', { level: t(`womens_safety.urgency_${preview.urgency}`) })}
          </span>
        </div>
      )}

      {error && <div className="text-sm text-red-600 dark:text-red-400 mb-2">{error}</div>}

      <button onClick={submit} disabled={submitting || !text.trim()}
        className="w-full text-sm font-semibold bg-fuchsia-600 hover:bg-fuchsia-700 disabled:opacity-50 text-white py-2 rounded-lg mb-3">
        {submitting ? t('womens_safety.submitting') : t('womens_safety.submit_button')}
      </button>

      {result && (
        <div className={`text-sm rounded-lg p-3 mb-3 ${result.escalated_incident_id ? 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300' : 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-300'}`}>
          {result.escalated_incident_id ? t('womens_safety.escalated_notice') : t('womens_safety.saved_notice')}
        </div>
      )}

      {reports.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-semibold text-slate-500 dark:text-slate-400">{t('womens_safety.history_title')}</div>
          {reports.slice(0, 5).map((r) => (
            <div key={r.id} className="border border-slate-100 dark:border-slate-700 rounded-lg p-2 text-xs">
              <div className="flex items-center justify-between mb-1">
                <span className="text-slate-500 dark:text-slate-400">{new Date(r.created_at).toLocaleString()}</span>
                <span className={`px-1.5 py-0.5 rounded-full font-semibold ${URGENCY_CLS[r.urgency]}`}>
                  {LABEL_ICON[r.sentiment_label] || '💬'} {t(`womens_safety.sentiment_${r.sentiment_label}`, r.sentiment_label)}
                </span>
              </div>
              <div className="text-slate-700 dark:text-slate-200 truncate">{r.text}</div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
