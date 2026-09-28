import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

import en from './locales/en.json'
import hi from './locales/hi.json'
import as_ from './locales/as.json'
import bn from './locales/bn.json'
import ta from './locales/ta.json'
import te from './locales/te.json'
import mr from './locales/mr.json'
import gu from './locales/gu.json'
import kn from './locales/kn.json'
import ml from './locales/ml.json'
import pa from './locales/pa.json'
import ja from './locales/ja.json'
import ko from './locales/ko.json'
import zh from './locales/zh.json'
import fr from './locales/fr.json'
import de from './locales/de.json'
import es from './locales/es.json'
import ru from './locales/ru.json'
import ar from './locales/ar.json'
import pt from './locales/pt.json'
import it from './locales/it.json'

// Language list surfaced in the switcher UI — native names, so a speaker of
// that language can find it without already reading English. The first 11
// are Indian languages; the rest match the Ministry of Tourism's own 1363
// tourist helpline language set (Japanese, Korean, Chinese, French, German,
// Spanish, Russian, Arabic, Portuguese, Italian).
export const SUPPORTED_LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'hi', label: 'हिन्दी' },
  { code: 'as', label: 'অসমীয়া' },
  { code: 'bn', label: 'বাংলা' },
  { code: 'ta', label: 'தமிழ்' },
  { code: 'te', label: 'తెలుగు' },
  { code: 'mr', label: 'मराठी' },
  { code: 'gu', label: 'ગુજરાતી' },
  { code: 'kn', label: 'ಕನ್ನಡ' },
  { code: 'ml', label: 'മലയാളം' },
  { code: 'pa', label: 'ਪੰਜਾਬੀ' },
  { code: 'ja', label: '日本語' },
  { code: 'ko', label: '한국어' },
  { code: 'zh', label: '中文' },
  { code: 'fr', label: 'Français' },
  { code: 'de', label: 'Deutsch' },
  { code: 'es', label: 'Español' },
  { code: 'ru', label: 'Русский' },
  { code: 'ar', label: 'العربية' },
  { code: 'pt', label: 'Português' },
  { code: 'it', label: 'Italiano' },
]

// Languages that read right-to-left -- scoped to the tourist-facing screens
// only (App.jsx sets `dir` on the document root; the admin/responder
// consoles are not translated and are used by Indian police operators, so
// RTL layout there is explicitly out of scope). See i18n.rtl.test.js.
export const RTL_LANGUAGES = ['ar']

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      hi: { translation: hi },
      as: { translation: as_ },
      bn: { translation: bn },
      ta: { translation: ta },
      te: { translation: te },
      mr: { translation: mr },
      gu: { translation: gu },
      kn: { translation: kn },
      ml: { translation: ml },
      pa: { translation: pa },
      ja: { translation: ja },
      ko: { translation: ko },
      zh: { translation: zh },
      fr: { translation: fr },
      de: { translation: de },
      es: { translation: es },
      ru: { translation: ru },
      ar: { translation: ar },
      pt: { translation: pt },
      it: { translation: it },
    },
    fallbackLng: 'en',
    interpolation: { escapeValue: false }, // React already escapes rendered output
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupLocalStorage: 'stsLang',
    },
  })

export default i18n
