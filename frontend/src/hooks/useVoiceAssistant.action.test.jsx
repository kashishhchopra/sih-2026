import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import '../i18n' // initializes i18next so t() resolves real strings, not raw keys
import api from '../api'
import useVoiceAssistant from './useVoiceAssistant'

const mock = new MockAdapter(api)

const mockSpeech = {
  supported: true, listening: false, transcript: '', error: null,
  start: vi.fn(), stop: vi.fn(), reset: vi.fn(),
}
vi.mock('./useSpeechRecognition', () => ({ default: () => mockSpeech }))
vi.mock('../lib/voiceService', () => ({
  speak: vi.fn(() => Promise.resolve()),
  stopSpeaking: vi.fn(),
  speechSynthesisSupported: () => true,
}))

beforeEach(() => {
  mock.reset()
  Object.assign(mockSpeech, { supported: true, listening: false, transcript: '', error: null })
})

// The optional action-router branch. Everything here is about proving it is
// purely ADDITIVE: without `onAction` the hook behaves exactly as it always
// has, and with it, only what the router claims is diverted.
describe('useVoiceAssistant onAction routing', () => {
  it('still sends everything to the backend when no onAction is given', async () => {
    mock.onPost('/copilot/ask').reply(200, { answer: 'Nearest hospital: City Hospital, 1.2 km.' })
    const { result } = renderHook(() => useVoiceAssistant({ endpoint: '/copilot/ask' }))

    await act(async () => { await result.current.ask('where is the nearest hospital') })

    expect(mock.history.post).toHaveLength(1)
    await waitFor(() => expect(result.current.exchanges[0].answer).toMatch(/City Hospital/))
  })

  it('lets a handled action answer without any backend round trip', async () => {
    mock.onPost('/copilot/ask').reply(200, { answer: 'should never be used' })
    const onAction = vi.fn(async () => 'Opening Plan.')
    const { result } = renderHook(() => useVoiceAssistant({ endpoint: '/copilot/ask', onAction }))

    await act(async () => { await result.current.ask('open my itinerary') })

    expect(onAction).toHaveBeenCalledWith('open my itinerary')
    expect(mock.history.post).toHaveLength(0) // the real action replaced the Q&A call
    await waitFor(() => expect(result.current.exchanges[0].answer).toBe('Opening Plan.'))
  })

  it('falls through to the backend when the router does not claim the text', async () => {
    mock.onPost('/copilot/ask').reply(200, { answer: 'This area is currently safe.' })
    const onAction = vi.fn(async () => null)
    const { result } = renderHook(() => useVoiceAssistant({ endpoint: '/copilot/ask', onAction }))

    await act(async () => { await result.current.ask('is this area safe') })

    expect(onAction).toHaveBeenCalled()
    expect(mock.history.post).toHaveLength(1)
    await waitFor(() => expect(result.current.exchanges[0].answer).toMatch(/currently safe/))
  })

  it('clears the thinking state after an action-handled turn', async () => {
    const onAction = vi.fn(async () => 'Done.')
    const { result } = renderHook(() => useVoiceAssistant({ endpoint: '/copilot/ask', onAction }))

    await act(async () => { await result.current.ask('go home') })

    await waitFor(() => expect(result.current.thinking).toBe(false))
  })
})
