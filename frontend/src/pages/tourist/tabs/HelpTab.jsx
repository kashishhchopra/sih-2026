import { useTranslation } from 'react-i18next'
import { Card } from '../../../components/ui.jsx'
import TabHero from '../../../components/TabHero.jsx'
import SafetyCardPanel from '../../../components/SafetyCardPanel.jsx'
import ConsularCard from '../../../components/ConsularCard.jsx'
import NearbyPlacesCard from '../../../components/NearbyPlacesCard.jsx'
import TranslateCard from '../../../components/TranslateCard.jsx'

// Everything a tourist reaches for in a moment of trouble that isn't the SOS
// button itself: offline emergency numbers, nearby police/hospital/pharmacy/
// transport, embassy contact for foreign tourists, on-the-spot translation,
// and the AI helper.
export default function HelpTab({ data, onAskAI }) {
  const { t } = useTranslation()
  const { nearby } = data

  return (
    <div className="space-y-4">
      <TabHero icon="🆘" title={t('help_hero.title')} subtitle={t('help_hero.subtitle')}
        gradient="from-teal-500 via-emerald-500 to-cyan-600" />

      <SafetyCardPanel touristId={data.tid} />
      <ConsularCard touristId={data.tid} />
      <NearbyPlacesCard touristId={data.tid} />
      <TranslateCard />

      <Card title={t('police.title')} icon="👮" iconColor="bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-300">
        <ul className="space-y-2">
          {nearby.map((u) => (
            <li key={u.id} className="flex items-center gap-3 text-sm">
              <span className="w-9 h-9 rounded-full bg-blue-50 dark:bg-blue-900/30 flex items-center justify-center text-base shrink-0">👮</span>
              <div className="flex-1 min-w-0">
                <div className="font-medium truncate">{u.name}</div>
                <div className="text-xs text-slate-500 dark:text-slate-400 truncate">{u.station} · ☎ {u.phone}</div>
              </div>
              <span className="text-xs font-semibold text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30 rounded-full px-2 py-0.5 shrink-0">
                {u.dist.toFixed(1)} km
              </span>
            </li>
          ))}
        </ul>
      </Card>

      <button onClick={onAskAI}
        className="w-full text-sm font-semibold text-white bg-gradient-to-r from-teal-500 to-cyan-600 hover:from-teal-600 hover:to-cyan-700 rounded-xl py-3 shadow-sm">
        {t('help.ask_safety_helper')}
      </button>
    </div>
  )
}
