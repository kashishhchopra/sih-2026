import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card } from './ui.jsx'
import { speak, speechSynthesisSupported } from '../lib/voiceService.js'
import {
  listGuideCategories, listGuidePhraseIds, translateGuidePhrase,
} from '../lib/translationService.js'

const CATEGORY_ICON = { greetings: '👋', directions: '🧭', food: '🍽️', shopping: '🛍️' }

// Multilingual Guide: an everyday phrasebook (greetings, directions, food,
// shopping) in the tourist's chosen language, beyond the safety-critical
// phrases TranslateCard already covers. See backend/services/translation.py.
export default function GuidePhrasebookCard({ lang }) {
  const { t } = useTranslation()
  const [categories, setCategories] = useState([])
  const [category, setCategory] = useState(null)
  const [phraseIds, setPhraseIds] = useState([])
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    listGuideCategories().then((cats) => {
      setCategories(cats)
      if (cats.length) setCategory(cats[0])
    }).catch(() => setError(t('guide.failed')))
  }, [t])

  useEffect(() => {
    if (!category) return
    listGuidePhraseIds(category).then(setPhraseIds).catch(() => setError(t('guide.failed')))
  }, [category, t])

  const say = (phraseId) => {
    setError('')
    translateGuidePhrase(category, phraseId, lang)
      .then((r) => {
        setResult(r)
        if (speechSynthesisSupported() && r?.text) speak(r.text, lang)
      })
      .catch(() => setError(t('guide.failed')))
  }

  return (
    <Card title={t('guide.card_title')} icon="📖" iconColor="bg-teal-50 text-teal-600 dark:bg-teal-900/30 dark:text-teal-300">
      <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">{t('guide.intro')}</p>
      {error && <div className="text-sm text-red-600 dark:text-red-400 mb-2">{error}</div>}

      <div className="flex flex-wrap gap-1.5 mb-3">
        {categories.map((c) => (
          <button key={c} onClick={() => { setCategory(c); setResult(null) }}
            className={`text-xs font-medium px-2.5 py-1.5 rounded-full ${category === c ? 'bg-teal-600 text-white' : 'bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200'}`}>
            {CATEGORY_ICON[c] || '💬'} {t(`guide.category_${c}`, c)}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap gap-1.5 mb-3">
        {phraseIds.map((id) => (
          <button key={id} onClick={() => say(id)}
            className="text-xs font-medium bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 px-2.5 py-1.5 rounded-full">
            {id.replace(/_/g, ' ')}
          </button>
        ))}
      </div>

      {result && (
        <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3 text-sm font-medium text-slate-800 dark:text-slate-100">
          {result.text ?? result.error}
        </div>
      )}
    </Card>
  )
}
