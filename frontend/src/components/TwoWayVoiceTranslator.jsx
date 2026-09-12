import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card } from './ui.jsx'
import useSpeechRecognition from '../hooks/useSpeechRecognition.js'
import { speak, speechSynthesisSupported } from '../lib/voiceService.js'
import { listLanguages, translateText as apiTranslateText } from '../lib/translationService.js'

// Two-way live voice translator: a conversation-mode translator for a
// tourist and a foreign traveler talking face-to-face -- each side speaks in
// their own language, the other side sees + hears it translated. Built
// entirely from pieces this app already has (useSpeechRecognition for STT,
// the browser's SpeechSynthesis for TTS via voiceService, and the existing
// /translate/text endpoint) -- no new backend surface needed.
function Speaker({ label, lang, onLangChange, languages, text, onHeard, disabled }) {
  const { t } = useTranslation()
  const sr = useSpeechRecognition({ lang: `${lang}-IN` })

  useEffect(() => {
    if (sr.transcript) {
      onHeard(sr.transcript)
      sr.reset()
    }
  }, [sr.transcript]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="border border-slate-100 dark:border-slate-700 rounded-lg p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold text-slate-600 dark:text-slate-300">{label}</span>
        <select value={lang} onChange={(e) => onLangChange(e.target.value)}
          className="text-xs border border-slate-200 dark:border-slate-600 dark:bg-slate-700 rounded-lg px-1.5 py-1">
          {Object.entries(languages).map(([code, name]) => <option key={code} value={code}>{name}</option>)}
        </select>
      </div>
      <button
        onClick={sr.listening ? sr.stop : sr.start}
        disabled={disabled || !sr.supported}
        className={`w-full text-sm font-semibold py-2 rounded-lg text-white disabled:opacity-50 ${sr.listening ? 'bg-red-600' : 'bg-sky-600 hover:bg-sky-700'}`}>
        {!sr.supported ? t('voice_translator.unsupported') : sr.listening ? t('voice_translator.listening') : t('voice_translator.tap_to_speak')}
      </button>
      {text && <div className="mt-2 text-sm bg-slate-50 dark:bg-slate-700/50 rounded-lg p-2">{text}</div>}
    </div>
  )
}

export default function TwoWayVoiceTranslator() {
  const { t } = useTranslation()
  const [languages, setLanguages] = useState({})
  const [langA, setLangA] = useState('en')
  const [langB, setLangB] = useState('hi')
  const [textA, setTextA] = useState('')
  const [textB, setTextB] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    listLanguages().then(setLanguages).catch(() => setError(t('voice_translator.failed')))
  }, [t])

  const handleHeard = (fromLang, toLang, setOwnText, setOtherText) => (heard) => {
    setOwnText(heard)
    setError('')
    apiTranslateText(heard, toLang, fromLang)
      .then((r) => {
        setOtherText(r.text)
        if (speechSynthesisSupported()) speak(r.text, toLang)
      })
      .catch(() => setError(t('voice_translator.failed')))
  }

  return (
    <Card title={t('voice_translator.card_title')} icon="🎙️" iconColor="bg-cyan-50 text-cyan-600 dark:bg-cyan-900/30 dark:text-cyan-300">
      <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">{t('voice_translator.intro')}</p>
      {error && <div className="text-sm text-red-600 dark:text-red-400 mb-2">{error}</div>}
      {Object.keys(languages).length > 0 && (
        <div className="grid grid-cols-1 gap-2">
          <Speaker label={t('voice_translator.you')} lang={langA} onLangChange={setLangA} languages={languages}
            text={textA} onHeard={handleHeard(langA, langB, setTextA, setTextB)} />
          <Speaker label={t('voice_translator.traveler')} lang={langB} onLangChange={setLangB} languages={languages}
            text={textB} onHeard={handleHeard(langB, langA, setTextB, setTextA)} />
        </div>
      )}
    </Card>
  )
}
