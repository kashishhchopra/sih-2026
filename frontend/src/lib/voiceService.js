// Central voice service: the one place that talks to the browser's
// text-to-speech engine, so pages don't each roll their own SpeechSynthesis
// logic. Speech-to-text already has its own hook (../hooks/useSpeechRecognition.js,
// wraps the Web Speech API's SpeechRecognition) -- this is TTS's counterpart,
// plus the small "is voice even usable here" check both share.
//
// No cloud speech API is called from here: `TEXT_TO_SPEECH_API_KEY` in the
// backend's .env.example is a placeholder for a future server-side voice if
// one is ever added, but the browser-native SpeechSynthesis API already
// covers every supported language with zero network calls and no key --
// using it is the honest choice, not a fallback for a missing feature.

export function speechSynthesisSupported() {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

// BCP-47 codes SpeechSynthesis expects, keyed by this app's own i18n codes
// (see frontend/src/locales/*.json) so callers can just pass i18n.language.
const LANG_TO_SPEECH_LOCALE = {
  en: 'en-IN', hi: 'hi-IN', fr: 'fr-FR', de: 'de-DE', es: 'es-ES',
  ja: 'ja-JP', zh: 'zh-CN', ko: 'ko-KR', ar: 'ar-SA', bn: 'bn-IN',
  ta: 'ta-IN', te: 'te-IN', mr: 'mr-IN', gu: 'gu-IN', kn: 'kn-IN',
  ml: 'ml-IN', pa: 'pa-IN', as: 'as-IN', it: 'it-IT', pt: 'pt-PT', ru: 'ru-RU',
}

/** Speak `text` aloud. No-op (resolves immediately) if the browser doesn't
 * support speech synthesis -- callers should never depend on this for
 * anything beyond a nice-to-have readout. */
export function speak(text, lang = 'en') {
  return new Promise((resolve) => {
    if (!speechSynthesisSupported() || !text) {
      resolve()
      return
    }
    window.speechSynthesis.cancel() // don't stack overlapping utterances
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = LANG_TO_SPEECH_LOCALE[lang] || 'en-IN'
    utterance.onend = resolve
    utterance.onerror = resolve
    window.speechSynthesis.speak(utterance)
  })
}

export function stopSpeaking() {
  if (speechSynthesisSupported()) window.speechSynthesis.cancel()
}
