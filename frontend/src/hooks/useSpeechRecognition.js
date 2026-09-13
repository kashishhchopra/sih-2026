import { useCallback, useRef, useState } from 'react'

// Thin wrapper over the Web Speech API for voice-driven emergency reporting.
// Browser support is inconsistent (no Firefox, prefixed in Chrome/Safari), so
// callers must check `supported` and fall back to a text input when false --
// this is a progressive enhancement, never the only way to send an SOS.
export default function useSpeechRecognition({ lang = 'en-IN' } = {}) {
  const [listening, setListening] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [error, setError] = useState(null)
  const recognitionRef = useRef(null)

  const SpeechRecognitionCtor =
    typeof window !== 'undefined'
      ? window.SpeechRecognition || window.webkitSpeechRecognition
      : null
  const supported = Boolean(SpeechRecognitionCtor)

  const start = useCallback(() => {
    if (!supported || listening) return
    setError(null)
    const recognition = new SpeechRecognitionCtor()
    recognition.lang = lang
    recognition.interimResults = false
    recognition.maxAlternatives = 1

    recognition.onresult = (event) => {
      const text = Array.from(event.results)
        .map((r) => r[0].transcript)
        .join(' ')
        .trim()
      setTranscript(text)
    }
    // Without this, a failure (mic permission denied, no microphone, the
    // browser refusing a second concurrent session) left the button stuck
    // showing "Listening..." forever with no visible error and no way to
    // retry -- indistinguishable from the button simply not working.
    recognition.onerror = (event) => {
      setError(event.error || 'speech-recognition-error')
      setListening(false)
    }
    recognition.onend = () => setListening(false)

    recognitionRef.current = recognition
    try {
      recognition.start()
      setListening(true)
    } catch (e) {
      // Some browsers throw synchronously (e.g. InvalidStateError) instead
      // of firing onerror -- must still be caught, or the button would look
      // clickable but silently do nothing.
      setError(e?.name || 'speech-recognition-error')
      setListening(false)
    }
  }, [SpeechRecognitionCtor, lang, listening, supported])

  const stop = useCallback(() => {
    recognitionRef.current?.stop()
  }, [])

  const reset = useCallback(() => setTranscript(''), [])

  return { supported, listening, transcript, error, start, stop, reset }
}
