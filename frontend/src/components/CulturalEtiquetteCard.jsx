import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card } from './ui.jsx'
import { speak, speechSynthesisSupported } from '../lib/voiceService.js'
import { listEtiquetteTopics, getEtiquetteTopic } from '../lib/etiquetteService.js'

const TOPIC_ICON = {
  greetings: '🙏', temples: '🛕', dress: '👕', dining: '🍽️', tipping: '💵', photography: '📷',
}

// Cultural Etiquette Guide: general, well-established do's/don'ts for a
// foreign tourist in India (greetings, temple visits, dress, dining,
// tipping, photography) -- curated, reviewed content, not a live guess.
// See backend/app/services/etiquette.py for the honesty rule: only
// English/Hindi are fully reviewed right now, everything else shows the
// English text with a visible note rather than a fabricated translation.
export default function CulturalEtiquetteCard({ lang }) {
  const { t } = useTranslation()
  const [topics, setTopics] = useState([])
  const [topic, setTopic] = useState(null)
  const [content, setContent] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    listEtiquetteTopics().then((ts) => {
      setTopics(ts)
      if (ts.length) setTopic(ts[0])
    }).catch(() => setError(t('etiquette.failed')))
  }, [t])

  useEffect(() => {
    if (!topic) return
    setError('')
    getEtiquetteTopic(topic, lang)
      .then(setContent)
      .catch(() => setError(t('etiquette.failed')))
  }, [topic, lang, t])

  const listen = () => {
    if (speechSynthesisSupported() && content?.text) speak(content.text, lang)
  }

  return (
    <Card title={t('etiquette.card_title')} icon="🤝" iconColor="bg-amber-50 text-amber-600 dark:bg-amber-900/30 dark:text-amber-300">
      <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">{t('etiquette.intro')}</p>
      {error && <div className="text-sm text-red-600 dark:text-red-400 mb-2">{error}</div>}

      <div className="flex flex-wrap gap-1.5 mb-3">
        {topics.map((tp) => (
          <button key={tp} onClick={() => { setTopic(tp); setContent(null) }}
            className={`text-xs font-medium px-2.5 py-1.5 rounded-full ${topic === tp ? 'bg-amber-600 text-white' : 'bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200'}`}>
            {TOPIC_ICON[tp] || '💬'} {t(`etiquette.topic_${tp}`, tp)}
          </button>
        ))}
      </div>

      {content && (
        <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3">
          <div className="flex items-center justify-between mb-1.5">
            <div className="font-semibold text-sm text-slate-800 dark:text-slate-100">{content.title}</div>
            {speechSynthesisSupported() && (
              <button onClick={listen} className="text-xs text-amber-700 dark:text-amber-400 font-medium">🔊 {t('etiquette.listen')}</button>
            )}
          </div>
          <p className="text-sm text-slate-700 dark:text-slate-200">{content.text}</p>
          {content.demo && (
            <div className="text-xs font-normal text-orange-600 dark:text-orange-400 mt-2">
              {t('etiquette.not_translated')}
            </div>
          )}
        </div>
      )}
    </Card>
  )
}
