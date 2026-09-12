import { useTranslation } from 'react-i18next'
import { SUPPORTED_LANGUAGES } from '../i18n'

export default function LanguageSwitcher({ className = '' }) {
  const { i18n } = useTranslation()

  return (
    <select
      value={i18n.resolvedLanguage || i18n.language}
      onChange={(e) => i18n.changeLanguage(e.target.value)}
      aria-label={SUPPORTED_LANGUAGES[0].label}
      className={`bg-transparent border border-white/30 rounded-lg text-xs px-2 py-1 ${className}`}
    >
      {SUPPORTED_LANGUAGES.map((l) => (
        <option key={l.code} value={l.code} className="text-slate-900">
          {l.label}
        </option>
      ))}
    </select>
  )
}
