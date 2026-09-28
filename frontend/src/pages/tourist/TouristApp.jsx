import { useCallback, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../auth.jsx'
import { detectIntent, INTENTS } from '../../lib/voiceIntent'
import useTouristData from './useTouristData.js'
import TouristShell from './TouristShell.jsx'
import TouristTabBar from './TouristTabBar.jsx'
import HomeTab from './tabs/HomeTab.jsx'
import PlanTab from './tabs/PlanTab.jsx'
import ExploreTab from './tabs/ExploreTab.jsx'
import HelpTab from './tabs/HelpTab.jsx'
import MeTab from './tabs/MeTab.jsx'
import ReportSheet from './tabs/ReportSheet.jsx'
import CopilotChat from '../../components/CopilotChat.jsx'
import VoiceAssistantButton from '../../components/VoiceAssistantButton.jsx'
import EmergencyModeCard from '../../components/EmergencyModeCard.jsx'

const TAB_COMPONENTS = { home: HomeTab, plan: PlanTab, explore: ExploreTab, help: HelpTab, me: MeTab }

// One calm screen (map + score + SOS) plus a five-tab bottom bar, instead of
// the ~15-card single scroll this used to be. Every feature that lived on
// that scroll still exists -- see useTouristData.js and pages/tourist/tabs/*
// -- only its location changed. All live data/mutations are in
// useTouristData so this component stays a thin shell.
export default function TouristApp() {
  const { user } = useAuth()
  const { t, i18n } = useTranslation()
  const tid = user.tourist_id
  const [activeTab, setActiveTab] = useState('home')
  const [reportOpen, setReportOpen] = useState(false)
  const copilotRef = useRef(null)
  const voiceRef = useRef(null)
  const data = useTouristData(tid)
  const { sendSOS } = data

  // Voice action router: only commands the app itself must *carry out*
  // (switch tab, raise a real SOS) are handled here -- everything else,
  // including every question about real data ("nearest hospital", "am I on
  // the right route"), returns null and falls through untouched to the
  // backend assistant that answers those from the database. Nothing is
  // fabricated here: the SOS goes through the very same sendSOS() the SOS
  // button calls, and the spoken confirmation reports its real response.
  const handleVoiceAction = useCallback(async (text) => {
    switch (detectIntent(text, i18n.resolvedLanguage || i18n.language)) {
      case INTENTS.SHOW_TOURIST_ID:
        setActiveTab('me')
        return t('voice_action.opening', { tab: t('nav.tab_me') })
      case INTENTS.SHOW_ITINERARY:
        setActiveTab('plan')
        return t('voice_action.opening', { tab: t('nav.tab_plan') })
      case INTENTS.GO_HOME:
      case INTENTS.GO_BACK:
        setActiveTab('home')
        return t('voice_action.opening', { tab: t('nav.tab_home') })
      case INTENTS.SEND_SOS: {
        const result = await sendSOS()
        if (result?.queued) return `${t('sos.queued_title')} ${t('sos.queued_body')}`
        const unit = result?.nearest_unit
        if (unit) {
          return `${t('sos.sent_title')}. ${t('sos.dispatched', {
            name: unit.name, station: unit.station, km: unit.distance_km,
          })}`
        }
        return t('sos.sent_title')
      }
      default:
        return null
    }
  }, [t, i18n.resolvedLanguage, i18n.language, sendSOS])

  if (!data.ready) {
    return <div className="p-6 text-center text-slate-500 dark:text-slate-400">{i18n.t('app.loading')}</div>
  }

  const ActiveTab = TAB_COMPONENTS[activeTab]

  return (
    <>
      <TouristShell
        digitalId={data.me.digital_id}
        online={data.online}
        toast={data.toast}
        onSOS={data.sendSOS}
        onReport={() => setReportOpen(true)}
        tid={tid}
        posRef={data.posRef}
      >
        <ActiveTab data={{ ...data, tid }} onAskAI={() => copilotRef.current?.open()}
          onVoice={() => voiceRef.current?.open()} onNavigateTab={setActiveTab} />
      </TouristShell>

      <TouristTabBar active={activeTab} onChange={setActiveTab} />

      <ReportSheet
        open={reportOpen}
        onClose={() => setReportOpen(false)}
        data={data}
        lang={i18n.resolvedLanguage || i18n.language}
      />

      {/* SOS live-location sharing: visible on any tab while an emergency
          is active (never for a silent/duress SOS -- see the component). */}
      <EmergencyModeCard sosSent={data.sosSent} tid={tid} posRef={data.posRef} />

      {/* Always-available voice assistant: one tap to speak, on any tab. */}
      <VoiceAssistantButton ref={voiceRef} touristId={tid} lang={i18n.resolvedLanguage || i18n.language}
        onAction={handleVoiceAction} />

      <CopilotChat ref={copilotRef} endpoint={`/tourists/${tid}/copilot/ask`} title="Safety Helper"
        placeholder="e.g. is this area safe?" lang={i18n.resolvedLanguage || i18n.language}
        suggestions={[
          'Nearest hospital?', 'Find transport', "What's my next destination?",
          'Show my itinerary', 'Am I on the correct route?', 'Is this area safe?',
        ]} />
    </>
  )
}
