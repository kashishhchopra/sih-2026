import { forwardRef, useImperativeHandle, useState } from 'react'
import { useTranslation } from 'react-i18next'
import useVoiceAssistant from '../hooks/useVoiceAssistant'

// AI Safety Copilot: a small chat panel shared by the control-room (against
// /copilot/ask) and the tourist app (against /tourists/{id}/copilot/ask).
// See app/services/copilot.py for the intent router behind both.
//
// Voice-enabled on the tourist side through the shared voice pipeline
// (../hooks/useVoiceAssistant -- the single place STT/intent/TTS lives, also
// used by the global VoiceAssistantButton): the mic button dictates a
// question and, when the speaker toggle is on, the reply is read back.
// Voice is a progressive enhancement throughout: every voice action has a
// typed/read equivalent right next to it, and nothing here is the only way
// to use the assistant.
//
// Exposes an imperative `open()` via ref so something other than its own
// floating button can trigger it -- e.g. the tourist dashboard hub's "Ask AI"
// card opens this exact same widget instead of duplicating a second one.
const CopilotChat = forwardRef(function CopilotChat(
  { endpoint, suggestions = [], title, placeholder, lang = 'en' }, ref
) {
  const { t } = useTranslation()
  const displayTitle = title ?? t('copilot.title')
  const displayPlaceholder = placeholder ?? t('copilot.placeholder')
  const [open, setOpen] = useState(false)
  useImperativeHandle(ref, () => ({ open: () => setOpen(true) }), [])
  const [input, setInput] = useState('')
  const voice = useVoiceAssistant({ endpoint, lang })
  const { thinking: loading } = voice

  // The chat renders a flat message list; the shared hook keeps
  // question/answer pairs, so flatten them here.
  const messages = voice.exchanges.flatMap((x) => [
    { role: 'user', text: x.question },
    ...(x.answer ? [{ role: 'assistant', text: x.answer }] : []),
  ])

  const ask = (question) => {
    if (!question.trim() || loading) return
    setInput('')
    voice.ask(question)
  }

  return (
    <>
      <button onClick={() => setOpen(true)}
        className="fixed bottom-[17rem] right-4 md:bottom-6 md:right-6 z-[1500] bg-sky-600 hover:bg-sky-700 text-white rounded-full w-14 h-14 shadow-lg flex items-center justify-center text-2xl">
        🤖
      </button>

      {open && (
        <div className="fixed inset-0 z-[2000] flex items-end md:items-center justify-center bg-black/40 p-0 md:p-4"
          onClick={() => setOpen(false)}>
          <div onClick={(e) => e.stopPropagation()}
            className="bg-white dark:bg-slate-800 w-full md:max-w-md md:rounded-2xl rounded-t-2xl shadow-2xl flex flex-col"
            style={{ height: 'min(600px, 85vh)' }}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 dark:border-slate-700">
              <div className="font-semibold text-slate-800 dark:text-slate-100">🤖 {displayTitle}</div>
              <div className="flex items-center gap-1">
                {voice.ttsSupported && (
                  <button onClick={voice.toggleSpeakReplies}
                    title={voice.speakReplies ? t('copilot.voice_replies_on') : t('copilot.voice_replies_off')}
                    className={`text-sm w-7 h-7 rounded-full flex items-center justify-center ${
                      voice.speakReplies ? 'bg-sky-100 dark:bg-sky-900/50' : 'text-slate-400'}`}>
                    {voice.speakReplies ? '🔊' : '🔈'}
                  </button>
                )}
                <button onClick={() => setOpen(false)} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 px-1">✕</button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {messages.length === 0 && (
                <div className="text-sm text-slate-400">
                  <p className="mb-2">{t('copilot.try_asking')}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {suggestions.map((s) => (
                      <button key={s} onClick={() => ask(s)}
                        className="text-xs bg-sky-50 dark:bg-sky-900/30 text-sky-700 dark:text-sky-300 rounded-full px-3 py-1.5 hover:bg-sky-100 dark:hover:bg-sky-900/50">
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {messages.map((m, i) => (
                <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm whitespace-pre-line ${
                    m.role === 'user'
                      ? 'bg-sky-600 text-white rounded-br-sm'
                      : 'bg-slate-100 dark:bg-slate-700 text-slate-800 dark:text-slate-100 rounded-bl-sm'}`}>
                    {m.text}
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex justify-start">
                  <div className="bg-slate-100 dark:bg-slate-700 rounded-2xl rounded-bl-sm px-3 py-2 text-sm text-slate-400">
                    {t('copilot.thinking')}
                  </div>
                </div>
              )}
              {voice.listening && (
                <div className="flex justify-end">
                  <div className="bg-sky-50 dark:bg-sky-900/30 text-sky-700 dark:text-sky-300 rounded-2xl rounded-br-sm px-3 py-2 text-sm flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-red-500 sos-pulse"></span> {t('copilot.listening')}
                  </div>
                </div>
              )}
              {voice.voiceError && (
                <div className="text-xs text-red-500 text-center">{t('copilot.voice_unavailable')}</div>
              )}
            </div>

            <form onSubmit={(e) => { e.preventDefault(); ask(input) }}
              className="flex items-center gap-2 p-3 border-t border-slate-100 dark:border-slate-700">
              {voice.micSupported && (
                <button type="button" onClick={voice.toggleMic}
                  title={voice.listening ? t('copilot.stop_listening') : t('copilot.ask_by_voice')}
                  className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 text-lg ${
                    voice.listening
                      ? 'bg-red-100 dark:bg-red-900/50 text-red-600 sos-pulse'
                      : 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300'}`}>
                  🎙️
                </button>
              )}
              <input value={input} onChange={(e) => setInput(e.target.value)} placeholder={displayPlaceholder}
                className="flex-1 border border-slate-300 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 rounded-full px-4 py-2 text-sm" />
              <button type="submit" disabled={loading || !input.trim()}
                className="bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white rounded-full w-9 h-9 flex items-center justify-center shrink-0">
                ➤
              </button>
            </form>
          </div>
        </div>
      )}
    </>
  )
})

export default CopilotChat
