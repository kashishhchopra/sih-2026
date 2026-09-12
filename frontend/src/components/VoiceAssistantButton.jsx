import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import useVoiceAssistant from '../hooks/useVoiceAssistant'
import { SUPPORTED_LANGUAGES } from '../i18n'

// Decorative level meter. The Web Speech API exposes no amplitude, so these
// bars signal "the mic is open" / "the assistant is talking" -- they are
// deliberately not presented as a real volume reading.
function VoiceBars({ className = '', bars = 5 }) {
  return (
    <div className={`flex items-end gap-[3px] h-5 ${className}`} aria-hidden="true">
      {Array.from({ length: bars }).map((_, i) => (
        <span key={i} className="voice-bar w-[3px] h-full rounded-full bg-current"
          style={{ animationDelay: `${i * 0.12}s` }} />
      ))}
    </div>
  )
}

// The always-available voice button: one tap starts listening anywhere in
// the tourist app, the answer is shown as text and (when the sound toggle
// is on) read back aloud. All of the actual pipeline lives in
// ../hooks/useVoiceAssistant -- this component is only its UI.
//
// It deliberately accepts ANY spoken sentence: nothing is matched or
// filtered here, the transcript goes straight to the backend assistant.
// The examples below are hints for a first-time user, not a command list.
const HINT_KEYS = [
  'voice_assistant.hint_hospital',
  'voice_assistant.hint_cab',
  'voice_assistant.hint_hotel',
  'voice_assistant.hint_route',
  'voice_assistant.hint_emergency',
]

const SOUND_KEY = 'voice-assistant-speak'
const HANDSFREE_KEY = 'voice-assistant-handsfree'

function storedFlag(key, fallback) {
  try {
    const raw = localStorage.getItem(key)
    return raw === null ? fallback : raw === '1'
  } catch {
    return fallback
  }
}

// `onAction` (optional) lets the host screen carry out a real in-app action
// for a recognised command -- switching tab, raising an actual SOS -- rather
// than answering it as a question. Omitted, everything behaves exactly as
// before: whatever was said goes straight to the backend assistant.
const VoiceAssistantButton = forwardRef(function VoiceAssistantButton({ touristId, lang = 'en', onAction }, ref) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  // Hands-free is on by default: the mic opens when the app loads and
  // reopens after each answer, so nothing has to be tapped. It stays a
  // toggle because an always-listening microphone is the tourist's call,
  // not ours.
  const [handsFree, setHandsFree] = useState(() => storedFlag(HANDSFREE_KEY, true))
  const voice = useVoiceAssistant({
    endpoint: `/tourists/${touristId}/copilot/ask`,
    lang,
    speakByDefault: storedFlag(SOUND_KEY, true),
    autoListen: handsFree,
    onAction,
  })

  useEffect(() => {
    try {
      localStorage.setItem(SOUND_KEY, voice.speakReplies ? '1' : '0')
    } catch {
      // best-effort: a blocked storage just means the preference won't stick
    }
  }, [voice.speakReplies])

  useEffect(() => {
    try {
      localStorage.setItem(HANDSFREE_KEY, handsFree ? '1' : '0')
    } catch {
      // best-effort, as above
    }
  }, [handsFree])

  const bottomRef = useRef(null)

  // Keep the newest exchange in view as the conversation grows. Guarded:
  // scrollIntoView is missing in some environments (jsdom, older webviews)
  // and this is pure polish -- it must never break the panel.
  useEffect(() => {
    const el = bottomRef.current
    if (typeof el?.scrollIntoView === 'function') el.scrollIntoView({ block: 'end' })
  }, [voice.exchanges])

  // Hands-free listens in the background -- the panel only comes up once
  // the tourist has actually said something, so opening the app doesn't
  // slam a dialog over the map.
  useEffect(() => {
    if (voice.exchanges.length > 0) setOpen(true)
  }, [voice.exchanges.length])

  // Lets the Home tab's "🎙️ Voice" quick action open this exact assistant
  // rather than a second copy of it.
  const startListening = () => {
    setOpen(true)
    if (!voice.listening) voice.toggleMic()
  }
  useImperativeHandle(ref, () => ({ open: startListening }))

  const languageLabel =
    SUPPORTED_LANGUAGES.find((l) => l.code === lang)?.label || lang.toUpperCase()

  const status = voice.listening ? 'listening'
    : voice.thinking ? 'thinking'
      : voice.speaking ? 'speaking'
        : 'idle'

  const STATUS_TEXT = {
    listening: t('voice_assistant.listening_speak_now'),
    thinking: t('voice_assistant.thinking'),
    speaking: t('voice_assistant.speaking'),
    idle: handsFree && !voice.autoBlocked ? t('voice_assistant.ready_just_speak') : t('voice_assistant.tap_mic_to_speak'),
  }

  return (
    <>
      {/* Sits clear above the SOS block (which spans ~110-170px from the
          bottom) and left of the AI chat bubble, so nothing covers the
          emergency button or the other assistant. */}
      <button
        onClick={startListening}
        aria-label={t('voice_assistant.aria_label')}
        className={`fixed bottom-48 right-4 md:bottom-6 md:right-24 z-[1500] rounded-full w-14 h-14 shadow-lg flex items-center justify-center text-2xl text-white transition-colors ${
          voice.listening
            ? 'bg-red-600 voice-listening-ring'
            : voice.speaking
              ? 'bg-sky-600 voice-speaking-ring'
              : 'bg-emerald-600 hover:bg-emerald-700'}`}>
        🎙️
      </button>

      {open && (
        <div className="fixed inset-0 z-[2000] flex items-end md:items-center justify-center bg-black/50 backdrop-blur-[2px]"
          onClick={() => setOpen(false)}>
          <div onClick={(e) => e.stopPropagation()} role="dialog" aria-label={t('voice_assistant.aria_label')}
            className="bg-white dark:bg-slate-800 w-full md:max-w-md md:rounded-3xl rounded-t-3xl shadow-2xl overflow-hidden">

            {/* ---- header: identity, current language, controls ---- */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 dark:border-slate-700">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-lg">🎙️</span>
                <div className="min-w-0">
                  <div className="font-semibold text-slate-800 dark:text-slate-100 leading-tight">
                    {t('voice_assistant.title')}
                  </div>
                  <div className="text-[11px] text-slate-400 truncate">
                    {t('voice_assistant.speaking_lang', { lang: languageLabel })}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                <span className="text-[11px] font-semibold px-2 py-1 rounded-full bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300">
                  🌐 {languageLabel}
                </span>
                <button onClick={() => setOpen(false)} aria-label={t('voice_assistant.close')}
                  className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 px-1 text-lg">✕</button>
              </div>
            </div>

            {/* ---- status strip: listening / thinking / speaking ---- */}
            <div className={`px-4 py-2.5 flex items-center gap-2.5 text-sm font-medium transition-colors ${
              status === 'listening' ? 'bg-red-50 dark:bg-red-900/25 text-red-600 dark:text-red-300'
                : status === 'speaking' ? 'bg-sky-50 dark:bg-sky-900/25 text-sky-700 dark:text-sky-300'
                  : status === 'thinking' ? 'bg-amber-50 dark:bg-amber-900/25 text-amber-700 dark:text-amber-300'
                    : 'bg-slate-50 dark:bg-slate-700/40 text-slate-500 dark:text-slate-400'}`}>
              {status === 'listening' && <VoiceBars />}
              {status === 'speaking' && <VoiceBars bars={4} />}
              {status === 'thinking' && (
                <span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
              )}
              <span aria-live="polite">{STATUS_TEXT[status]}</span>
            </div>

            <div className="px-4 py-3 space-y-3 max-h-[52vh] overflow-y-auto">
              {!voice.micSupported && (
                <div className="text-xs text-orange-600 dark:text-orange-400 bg-orange-50 dark:bg-orange-900/25 rounded-lg p-2.5">
                  {t('voice_assistant.no_voice_support')}
                </div>
              )}
              {handsFree && voice.autoBlocked && (
                <div className="text-xs text-orange-600 dark:text-orange-400 bg-orange-50 dark:bg-orange-900/25 rounded-lg p-2.5">
                  {t('voice_assistant.tap_mic_once')}
                </div>
              )}
              {voice.voiceError && !voice.autoBlocked && (
                <div className="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/25 rounded-lg p-2.5">
                  {t('voice_assistant.mic_unavailable')}
                </div>
              )}

              {/* ---- transcript + response, oldest first ---- */}
              {voice.exchanges.map((x, i) => (
                <div key={i} className="space-y-1.5">
                  <div className="flex justify-end">
                    <div className="max-w-[85%] bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-2xl rounded-br-sm px-3 py-2 text-sm">
                      {x.question}
                    </div>
                  </div>
                  {x.answer && (
                    <div className="flex justify-start">
                      <div className="max-w-[90%] bg-emerald-50 dark:bg-emerald-900/25 text-slate-800 dark:text-slate-100 rounded-2xl rounded-bl-sm px-3 py-2 text-sm whitespace-pre-line">
                        {x.answer}
                      </div>
                    </div>
                  )}
                </div>
              ))}

              {/* Live partial transcript while the tourist is still talking. */}
              {voice.listening && voice.transcript && (
                <div className="flex justify-end">
                  <div className="max-w-[85%] border border-dashed border-slate-300 dark:border-slate-600 text-slate-500 dark:text-slate-400 rounded-2xl px-3 py-2 text-sm italic">
                    {voice.transcript}
                  </div>
                </div>
              )}

              {/* ---- suggested commands: tappable, not just examples ---- */}
              {voice.exchanges.length === 0 && (
                <div>
                  <p className="text-xs text-slate-400 mb-2">
                    {t('voice_assistant.ask_anything')}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {HINT_KEYS.map((k) => (
                      <button key={k} onClick={() => voice.ask(t(k))}
                        className="text-xs bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 rounded-full px-3 py-1.5 hover:bg-emerald-100 dark:hover:bg-emerald-900/50">
                        {t(k)}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            {/* ---- controls ---- */}
            <div className="border-t border-slate-100 dark:border-slate-700 p-4 space-y-3">
              <div className="flex items-center justify-center gap-4">
                {voice.exchanges.length > 0 && (
                  <button onClick={voice.clear} className="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300">
                    {t('voice_assistant.clear')}
                  </button>
                )}
                <button onClick={voice.toggleMic} disabled={!voice.micSupported}
                  aria-label={voice.listening ? t('voice_assistant.stop_listening') : t('voice_assistant.start_listening')}
                  className={`relative rounded-full w-16 h-16 flex items-center justify-center text-2xl text-white shadow-lg disabled:opacity-50 transition-colors ${
                    voice.listening
                      ? 'bg-red-600 voice-listening-ring'
                      : 'bg-emerald-600 hover:bg-emerald-700'}`}>
                  {voice.listening ? '■' : '🎙️'}
                </button>
                {voice.speaking && (
                  <button onClick={voice.toggleSpeakReplies}
                    className="text-xs text-sky-600 dark:text-sky-400 hover:underline">
                    {t('voice_assistant.stop')}
                  </button>
                )}
              </div>

              <div className="flex items-center justify-center gap-2">
                <button onClick={() => setHandsFree((v) => !v)}
                  aria-pressed={handsFree}
                  title={handsFree ? t('voice_assistant.hands_free_on_title') : t('voice_assistant.hands_free_off_title')}
                  className={`text-xs font-semibold px-3 py-1.5 rounded-full ${
                    handsFree
                      ? 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300'
                      : 'bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400'}`}>
                  {handsFree ? t('voice_assistant.hands_free_on') : t('voice_assistant.hands_free_off')}
                </button>
                {voice.ttsSupported && (
                  <button onClick={voice.toggleSpeakReplies}
                    aria-pressed={voice.speakReplies}
                    title={voice.speakReplies ? t('voice_assistant.sound_on_title') : t('voice_assistant.sound_off_title')}
                    className={`text-xs font-semibold px-3 py-1.5 rounded-full ${
                      voice.speakReplies
                        ? 'bg-sky-100 dark:bg-sky-900/40 text-sky-700 dark:text-sky-300'
                        : 'bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400'}`}>
                    {voice.speakReplies ? t('voice_assistant.sound_on') : t('voice_assistant.sound_off')}
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
})

export default VoiceAssistantButton
