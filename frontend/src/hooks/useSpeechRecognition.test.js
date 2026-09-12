import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import useSpeechRecognition from './useSpeechRecognition'

class FakeRecognition {
  constructor() {
    this.lang = ''
    this.interimResults = false
    this.maxAlternatives = 1
    this.started = false
    FakeRecognition.instances.push(this)
  }
  start() { this.started = true }
  stop() { this.onend?.() }
  // Test helper: simulate the browser delivering a transcript.
  emitResult(text) {
    this.onresult?.({ results: [[{ transcript: text }]] })
  }
  emitError(code) {
    this.onerror?.({ error: code })
  }
}
FakeRecognition.instances = []

describe('useSpeechRecognition', () => {
  beforeEach(() => {
    FakeRecognition.instances = []
  })
  afterEach(() => {
    delete window.SpeechRecognition
    delete window.webkitSpeechRecognition
  })

  it('reports unsupported when neither global exists', () => {
    const { result } = renderHook(() => useSpeechRecognition())
    expect(result.current.supported).toBe(false)
  })

  it('reports supported via the webkit-prefixed global', () => {
    window.webkitSpeechRecognition = FakeRecognition
    const { result } = renderHook(() => useSpeechRecognition())
    expect(result.current.supported).toBe(true)
  })

  it('start() is a no-op when unsupported', () => {
    const { result } = renderHook(() => useSpeechRecognition())
    act(() => result.current.start())
    expect(result.current.listening).toBe(false)
    expect(FakeRecognition.instances).toHaveLength(0)
  })

  it('starts listening and captures a transcript', () => {
    window.SpeechRecognition = FakeRecognition
    const { result } = renderHook(() => useSpeechRecognition())

    act(() => result.current.start())
    expect(result.current.listening).toBe(true)
    expect(FakeRecognition.instances[0].started).toBe(true)

    act(() => FakeRecognition.instances[0].emitResult('help I am lost'))
    expect(result.current.transcript).toBe('help I am lost')
  })

  it('stops listening when the engine signals end', () => {
    window.SpeechRecognition = FakeRecognition
    const { result } = renderHook(() => useSpeechRecognition())
    act(() => result.current.start())
    act(() => FakeRecognition.instances[0].onend())
    expect(result.current.listening).toBe(false)
  })

  it('surfaces an error and stops listening', () => {
    window.SpeechRecognition = FakeRecognition
    const { result } = renderHook(() => useSpeechRecognition())
    act(() => result.current.start())
    act(() => FakeRecognition.instances[0].emitError('no-speech'))
    act(() => FakeRecognition.instances[0].onend())
    expect(result.current.error).toBe('no-speech')
    expect(result.current.listening).toBe(false)
  })

  it('reset() clears the transcript', () => {
    window.SpeechRecognition = FakeRecognition
    const { result } = renderHook(() => useSpeechRecognition())
    act(() => result.current.start())
    act(() => FakeRecognition.instances[0].emitResult('some text'))
    act(() => result.current.reset())
    expect(result.current.transcript).toBe('')
  })

  it('passes the configured language to the recognition engine', () => {
    window.SpeechRecognition = FakeRecognition
    const { result } = renderHook(() => useSpeechRecognition({ lang: 'hi-IN' }))
    act(() => result.current.start())
    expect(FakeRecognition.instances[0].lang).toBe('hi-IN')
  })

  it('does not start a second recognition while already listening', () => {
    window.SpeechRecognition = FakeRecognition
    const { result } = renderHook(() => useSpeechRecognition())
    act(() => result.current.start())
    act(() => result.current.start())
    expect(FakeRecognition.instances).toHaveLength(1)
  })
})
