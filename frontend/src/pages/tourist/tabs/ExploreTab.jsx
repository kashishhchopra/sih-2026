import { useTranslation } from 'react-i18next'
import TabHero from '../../../components/TabHero.jsx'
import TripPlannerCard from '../../../components/TripPlannerCard.jsx'
import CrowdForecastCard from '../../../components/CrowdForecastCard.jsx'
import DiscoveryCard from '../../../components/DiscoveryCard.jsx'
import OfflineTripCard from '../../../components/OfflineTripCard.jsx'
import GuidePhrasebookCard from '../../../components/GuidePhrasebookCard.jsx'
import TwoWayVoiceTranslator from '../../../components/TwoWayVoiceTranslator.jsx'
import FestivalCalendarCard from '../../../components/FestivalCalendarCard.jsx'
import PermitCard from '../../../components/PermitCard.jsx'
import FairPriceCard from '../../../components/FairPriceCard.jsx'
import CulturalEtiquetteCard from '../../../components/CulturalEtiquetteCard.jsx'
import CurrencyCard from '../../../components/CurrencyCard.jsx'
import { DEFAULT_MAP } from '../../../config.js'

// Explore: trip planning, crowd/queue forecasting, off-the-beaten-path
// discovery, the multilingual phrasebook, a two-way voice translator, the
// local festival calendar, and permit/e-pass automation -- everything about
// planning and enriching the trip itself, distinct from PlanTab's
// safety-route planning and HelpTab's emergency assistance.
export default function ExploreTab({ data }) {
  const { t, i18n } = useTranslation()
  const { me, tid } = data
  const lat = me?.last_lat ?? DEFAULT_MAP.center[0]
  const lng = me?.last_lng ?? DEFAULT_MAP.center[1]
  const lang = i18n.resolvedLanguage || i18n.language

  return (
    <div className="space-y-4">
      <TabHero icon="🌍" title={t('explore_hero.title')} subtitle={t('explore_hero.subtitle')}
        gradient="from-emerald-500 via-teal-500 to-cyan-600" />

      <TripPlannerCard touristId={tid} />
      <CrowdForecastCard />
      <DiscoveryCard lat={lat} lng={lng} />
      <OfflineTripCard touristId={tid} me={me} lat={lat} lng={lng} />
      <FestivalCalendarCard lat={lat} lng={lng} />
      <GuidePhrasebookCard lang={lang} />
      <TwoWayVoiceTranslator />
      <CulturalEtiquetteCard lang={lang} />
      <CurrencyCard />
      <FairPriceCard touristId={tid} lat={lat} lng={lng} />
      <PermitCard touristId={tid} />
    </div>
  )
}
