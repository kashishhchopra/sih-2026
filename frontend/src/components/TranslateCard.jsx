import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card } from './ui.jsx'
import { speak, speechSynthesisSupported } from '../lib/voiceService.js'
import { listLanguages, listPhraseIds, translatePhrase as apiTranslatePhrase, translateText as apiTranslateText } from '../lib/translationService.js'

// Multilingual translation: curated, reviewed safety phrases (works with no
// external API key -- see backend/services/translation.py) plus free-text
// translation that is honestly labelled "demo" (original text shown
// unmodified) whenever no live translation API is configured, rather than
// ever fabricating a translation.
export default function TranslateCard() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [languages, setLanguages] = useState({})
  const [phraseIds, setPhraseIds] = useState([])
  const [lang, setLang] = useState('hi')
  const [result, setResult] = useState(null)
  const [text, setText] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open || Object.keys(languages).length) return
    Promise.all([listLanguages(), listPhraseIds()])
      .then(([l, p]) => { setLanguages(l); setPhraseIds(p) })
      .catch(() => setError(t('translate.service_unavailable')))
  }, [open, languages, t])

  const say = (r) => {
    if (speechSynthesisSupported() && r?.text) speak(r.text, lang)
  }

  const translatePhrase = (phraseId) => {
    setError('')
    apiTranslatePhrase(phraseId, lang)
      .then((r) => { setResult(r); say(r) })
      .catch(() => setError(t('translate.phrase_failed')))
  }

  const translateText = () => {
    if (!text.trim()) return
    setError('')
    apiTranslateText(text, lang)
      .then((r) => { setResult(r); say(r) })
      .catch(() => setError(t('translate.text_failed')))
  }

  return (
    <div>
      <button onClick={() => setOpen((v) => !v)}
        className="w-full text-sm font-semibold text-sky-700 dark:text-sky-400 bg-sky-50 dark:bg-sky-900/30 rounded-xl py-2">
        {open ? t('translate.toggle_hide') : t('translate.toggle_show')}
      </button>

      {open && (
        <div className="mt-3">
          <Card title={t('translate.card_title')}>
            {error && <div className="text-sm text-red-600 dark:text-red-400 mb-2">{error}</div>}

            {Object.keys(languages).length > 0 && (
              <select value={lang} onChange={(e) => setLang(e.target.value)}
                className="w-full text-sm border border-slate-200 dark:border-slate-600 dark:bg-slate-700 rounded-lg px-2 py-1.5 mb-3">
                {Object.entries(languages).map(([code, name]) => (
                  <option key={code} value={code}>{name}</option>
                ))}
              </select>
            )}

            {phraseIds.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-3">
                {phraseIds.map((id) => (
                  <button key={id} onClick={() => translatePhrase(id)}
                    className="text-xs font-medium bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 px-2.5 py-1.5 rounded-full">
                    {id.replace(/_/g, ' ')}
                  </button>
                ))}
              </div>
            )}

            <div className="flex gap-2 mb-3">
              <input value={text} onChange={(e) => setText(e.target.value)}
                placeholder={t('translate.input_placeholder')}
                className="flex-1 text-sm border border-slate-200 dark:border-slate-600 dark:bg-slate-700 rounded-lg px-2 py-1.5" />
              <button onClick={translateText}
                className="text-xs font-semibold bg-sky-600 hover:bg-sky-700 text-white px-3 rounded-lg">{t('translate.go')}</button>
            </div>

            {result && (
              <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3 text-sm">
                <div className="font-medium text-slate-800 dark:text-slate-100">{result.text ?? result.error}</div>
                {result.demo && (
                  <div className="text-xs text-orange-600 dark:text-orange-400 mt-1">
                    {t('translate.demo_mode', { note: result.note || t('translate.demo_fallback_note') })}
                  </div>
                )}
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  )
}
