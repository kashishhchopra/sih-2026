import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import api from '../api'
import useSpeechRecognition from './useSpeechRecognition'
import { speak, speechSynthesisSupported, stopSpeaking } from '../lib/voiceService'

// THE central voice pipeline for the whole tourist app. Every screen that
// offers voice goes through this hook, so microphone/TTS logic exists in
// exactly one place (this file plus its two primitives:
// ./useSpeechRecognition for STT and ../lib/voiceService for TTS) -- no
// page implements its own.
//
//   speech input -> speech-to-text (Web Speech API)
//                -> intent detection (backend services/copilot.py)
//                -> application action + text response
//                -> text-to-speech (SpeechSynthesis)
//
// Nothing here restricts what the tourist may say: whatever the recognizer
// returns is sent verbatim to the backend, which decides how to answer.
// There is no fixed client-side command list, and no phrase is special-
// cased in the UI.

// Errors that mean the microphone genuinely cannot be used, as opposed to
// "you didn't say anything" -- see the autoBlocked effect below.
const FATAL_MIC_ERRORS = new Set(['not-allowed', 'service-not-allowed', 'audio-capture'])

export default function useVoiceAssistant({
  endpoint, lang = 'en', speakByDefault = false, autoListen = false,
  // Optional action router. When supplied, a transcript is offered to it
  // FIRST; if it returns a string, that string is the answer and no
  // backend call is made -- this is how "send an SOS" or "open my
  // itinerary" perform a real in-app action instead of being answered as
  // a question. Returning null/undefined (or omitting the prop entirely,
  // as every pre-existing caller does) leaves behaviour exactly as before:
  // everything goes to the Q&A endpoint, nothing is filtered client-side.
  onAction,
} = {}) {
  const { t } = useTranslation()
  const [exchanges, setExchanges] = useState([]) // {question, answer}
  const [thinking, setThinking] = useState(false)
  const [speakReplies, setSpeakReplies] = useState(speakByDefault)
  const [autoBlocked, setAutoBlocked] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  const speech = useSpeechRecognition({ lang: `${lang}-IN` })
  const lastHandledRef = useRef('')
  const startedRef = useRef(false)

  // Bounded, flattened prior turns to send with the next question -- lets
  // the backend resolve a bare "yes" against what it just offered (see
  // backend/app/services/copilot.py:resolve_followup) instead of every
  // question being answered with no memory of the one before it. Only
  // completed exchanges (a real answer already came back); the in-flight
  // one being asked right now is the `question` param itself, not history.
  const historyPayload = useCallback(() => {
    const turns = exchanges
      .filter((x) => x.answer)
      .flatMap((x) => [{ role: 'user', text: x.question }, { role: 'assistant', text: x.answer }])
    return turns.slice(-10)
  }, [exchanges])

  // Sending is deliberately independent of the microphone: a typed question
  // and a spoken one take the exact same path from here on.
  const ask = useCallback(async (question) => {
    const text = (question || '').trim()
    if (!text) return null
    const history = historyPayload()
    setExchanges((e) => [...e, { question: text, answer: null }])
    setThinking(true)

    // An action the app itself can carry out (navigate, raise a real SOS)
    // short-circuits the Q&A round trip -- see `onAction` above.
    if (onAction) {
      const actionAnswer = await onAction(text)
      if (actionAnswer) {
        setExchanges((e) => e.map((x, i) => (i === e.length - 1 ? { ...x, answer: actionAnswer } : x)))
        if (speakReplies) {
          setSpeaking(true)
          speak(actionAnswer, lang).finally(() => setSpeaking(false))
        }
        setThinking(false)
        return actionAnswer
      }
    }

    try {
      const { data } = await api.post(endpoint, { question: text, history })
      setExchanges((e) => e.map((x, i) => (i === e.length - 1 ? { ...x, answer: data.answer } : x)))
      if (speakReplies) {
        setSpeaking(true)
        speak(data.answer, lang).finally(() => setSpeaking(false))
      }
      return data.answer
    } catch {
      const failText = t('voice_assistant.request_failed')
      setExchanges((e) => e.map((x, i) => (i === e.length - 1 ? { ...x, answer: failText } : x)))
      if (speakReplies) {
        setSpeaking(true)
        speak(failText, lang).finally(() => setSpeaking(false))
      }
      return failText
    } finally {
      setThinking(false)
    }
  }, [endpoint, lang, speakReplies, t, onAction, historyPayload])

  // Push-to-talk. Speaking is stopped first so the assistant never talks
  // over the tourist (and never records its own voice).
  const toggleMic = useCallback(() => {
    if (speech.listening) {
      speech.stop()
      return
    }
    // A tap is a user gesture, so the browser can prompt for permission
    // again -- give hands-free another chance from here.
    setAutoBlocked(false)
    stopSpeaking()
    setSpeaking(false)
    speech.reset()
    lastHandledRef.current = ''
    speech.start()
  }, [speech])

  // Send automatically once recognition finishes -- no separate "send" tap
  // after speaking. Guarded so one transcript is only ever sent once.
  useEffect(() => {
    const text = (speech.transcript || '').trim()
    if (speech.listening || !text || thinking) return
    if (lastHandledRef.current === text) return
    lastHandledRef.current = text
    ask(text)
  }, [speech.listening, speech.transcript, thinking, ask])

  // Hands-free mode. The microphone opens on its own when the app loads and
  // reopens after each answer, so the tourist never has to tap anything.
  //
  // Two hard constraints shape this:
  //  * A browser refuses getUserMedia without a prior permission grant for
  //    the origin, so the very first visit still needs one tap. When that
  //    happens `autoBlocked` goes true and we STOP trying -- retrying in a
  //    loop would spam permission errors and drain the battery.
  //  * We never reopen the mic while the assistant is speaking, or it would
  //    transcribe its own voice back as the next question.
  const startListening = useCallback(() => {
    stopSpeaking()
    setSpeaking(false)
    speech.reset()
    lastHandledRef.current = ''
    speech.start()
  }, [speech])

  useEffect(() => {
    if (!autoListen || autoBlocked || startedRef.current) return
    if (!speech.supported) return
    startedRef.current = true
    startListening()
  }, [autoListen, autoBlocked, speech.supported, startListening])

  // Only a real permission/hardware refusal disables hands-free. "no-speech"
  // and "aborted" are the normal end of a listening window with nothing said
  // -- treating those as failures would switch the feature off the first
  // time the tourist simply stayed quiet.
  useEffect(() => {
    if (speech.error && FATAL_MIC_ERRORS.has(speech.error)) setAutoBlocked(true)
  }, [speech.error])

  // Reopen the mic once an answer is delivered (and finished being read
  // aloud, if the sound toggle is on).
  useEffect(() => {
    if (!autoListen || autoBlocked || thinking || speech.listening) return
    const last = exchanges[exchanges.length - 1]
    if (!last?.answer) return
    const delayMs = speakReplies ? 900 : 250
    const timer = setTimeout(() => {
      if (!speechSynthesisSupported() || !window.speechSynthesis.speaking) startListening()
    }, delayMs)
    return () => clearTimeout(timer)
  }, [autoListen, autoBlocked, thinking, speech.listening, exchanges, speakReplies, startListening])

  const toggleSpeakReplies = useCallback(() => {
    setSpeakReplies((v) => {
      if (v) {
        stopSpeaking()
        setSpeaking(false)
      }
      return !v
    })
  }, [])

  const clear = useCallback(() => {
    setExchanges([])
    speech.reset()
    lastHandledRef.current = ''
    stopSpeaking()
    setSpeaking(false)
  }, [speech])

  return {
    exchanges,
    thinking,
    ask,
    clear,
    // microphone
    micSupported: speech.supported,
    listening: speech.listening,
    transcript: speech.transcript,
    voiceError: speech.error,
    toggleMic,
    // hands-free
    autoBlocked,
    // speech output
    ttsSupported: speechSynthesisSupported(),
    speaking,
    lang,
    speakReplies,
    toggleSpeakReplies,
  }
}
