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
    recognition.onerror = (event) => setError(event.error || 'speech-recognition-error')
    recognition.onend = () => setListening(false)

    recognitionRef.current = recognition
    setListening(true)
    recognition.start()
  }, [SpeechRecognitionCtor, lang, listening, supported])

  const stop = useCallback(() => {
    recognitionRef.current?.stop()
  }, [])

  const reset = useCallback(() => setTranscript(''), [])

  return { supported, listening, transcript, error, start, stop, reset }
}
