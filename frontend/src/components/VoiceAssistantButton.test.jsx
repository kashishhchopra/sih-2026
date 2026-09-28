import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, fireEvent, waitFor } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import api from '../api'
import VoiceAssistantButton from './VoiceAssistantButton'

const mock = new MockAdapter(api)

// The shared voice pipeline's two primitives are mocked here, exactly as a
// browser without/with Web Speech support would behave.
const mockSpeech = {
  supported: true, listening: false, transcript: '', error: null,
  start: vi.fn(), stop: vi.fn(), reset: vi.fn(),
}
vi.mock('../hooks/useSpeechRecognition', () => ({
  default: () => mockSpeech,
}))
vi.mock('../lib/voiceService', () => ({
  speak: vi.fn(() => Promise.resolve()),
  stopSpeaking: vi.fn(),
  speechSynthesisSupported: () => true,
}))

import { speak } from '../lib/voiceService'

beforeEach(() => {
  mock.reset()
  localStorage.clear()
  speak.mockClear()
  Object.assign(mockSpeech, {
    supported: true, listening: false, transcript: '', error: null,
  })
  mockSpeech.start.mockClear()
  mockSpeech.stop.mockClear()
})

describe('VoiceAssistantButton', () => {
  it('renders a floating mic button on every screen', () => {
    const { getByLabelText } = render(<VoiceAssistantButton touristId={1} />)
    expect(getByLabelText('Voice assistant')).toBeInTheDocument()
  })

  it('starts listening as soon as the mic button is tapped', () => {
    const { getByLabelText, getByRole } = render(<VoiceAssistantButton touristId={1} />)
    fireEvent.click(getByLabelText('Voice assistant'))
    expect(mockSpeech.start).toHaveBeenCalled()
    expect(getByRole('dialog', { name: 'Voice assistant' })).toBeInTheDocument()
  })

  it('sends whatever the tourist said verbatim and shows the answer', async () => {
    mock.onPost('/tourists/1/copilot/ask').reply(200, { answer: 'Nearest pharmacy: City Pharmacy, 0.4 km away.' })
    const { getByLabelText, findByText, rerender } = render(<VoiceAssistantButton touristId={1} />)
    fireEvent.click(getByLabelText('Voice assistant'))

    // Recognition finishes with an arbitrary sentence (nothing client-side
    // matches or filters it).
    mockSpeech.listening = false
    mockSpeech.transcript = 'is there a chemist shop around here somewhere'
    rerender(<VoiceAssistantButton touristId={1} />)

    await findByText(/City Pharmacy/)
    expect(JSON.parse(mock.history.post[0].data).question)
      .toBe('is there a chemist shop around here somewhere')
  })

  it('reads the reply aloud by default, and goes quiet once sound is switched off', async () => {
    mock.onPost('/tourists/1/copilot/ask').reply(200, { answer: 'You are on your planned route.' })
    const { getByLabelText, getByText, findByText, rerender } = render(<VoiceAssistantButton touristId={1} />)
    fireEvent.click(getByLabelText('Voice assistant'))
    expect(getByText('🔊 Sound on')).toBeInTheDocument()

    mockSpeech.listening = false
    mockSpeech.transcript = 'am i on the correct route'
    rerender(<VoiceAssistantButton touristId={1} />)
    await findByText(/planned route/)
    await waitFor(() => expect(speak).toHaveBeenCalledWith('You are on your planned route.', 'en'))

    // Switch sound off -- the next answer must not be spoken.
    fireEvent.click(getByText('🔊 Sound on'))
    await waitFor(() => expect(getByText('🔈 Sound off')).toBeInTheDocument())
    speak.mockClear()
    mockSpeech.transcript = 'am i still on the correct route'
    rerender(<VoiceAssistantButton touristId={1} />)
    await findByText(/planned route/)
    expect(speak).not.toHaveBeenCalled()
  })

  it('remembers the sound preference across remounts', async () => {
    mock.onPost('/tourists/1/copilot/ask').reply(200, { answer: 'ok' })
    const { getByLabelText, getByText, unmount } = render(<VoiceAssistantButton touristId={1} />)
    fireEvent.click(getByLabelText('Voice assistant'))
    fireEvent.click(getByText('🔊 Sound on'))
    await waitFor(() => expect(getByText('🔈 Sound off')).toBeInTheDocument())
    unmount()

    const second = render(<VoiceAssistantButton touristId={1} />)
    fireEvent.click(second.getByLabelText('Voice assistant'))
    expect(second.getByText('🔈 Sound off')).toBeInTheDocument()
  })

  it('explains itself when the browser has no speech recognition', () => {
    mockSpeech.supported = false
    const { getByLabelText, getByText } = render(<VoiceAssistantButton touristId={1} />)
    fireEvent.click(getByLabelText('Voice assistant'))
    expect(getByText(/doesn't support voice input/)).toBeInTheDocument()
  })

  it('surfaces a microphone permission error instead of failing silently', () => {
    mockSpeech.error = 'not-allowed'
    const { getByLabelText, getByText } = render(<VoiceAssistantButton touristId={1} />)
    fireEvent.click(getByLabelText('Voice assistant'))
    expect(getByText(/Microphone unavailable/)).toBeInTheDocument()
  })

  it('shows a fallback answer when the assistant request fails', async () => {
    mock.onPost('/tourists/1/copilot/ask').reply(500)
    const { getByLabelText, findByText, rerender } = render(<VoiceAssistantButton touristId={1} />)
    fireEvent.click(getByLabelText('Voice assistant'))
    mockSpeech.listening = false
    mockSpeech.transcript = 'find a cab'
    rerender(<VoiceAssistantButton touristId={1} />)
    await findByText(/could not process that/)
  })
})

describe('VoiceAssistantButton hands-free', () => {
  it('starts listening on its own when the app opens, with no tap', async () => {
    mock.onPost('/tourists/1/copilot/ask').reply(200, { answer: 'ok' })
    render(<VoiceAssistantButton touristId={1} />)
    await waitFor(() => expect(mockSpeech.start).toHaveBeenCalled())
  })

  it('surfaces the panel only once something is actually said', async () => {
    mock.onPost('/tourists/1/copilot/ask').reply(200, { answer: 'Bihu is a harvest festival.' })
    const { queryByRole, findByText, rerender } = render(<VoiceAssistantButton touristId={1} />)
    // Listening in the background -- no dialog covering the app yet.
    expect(queryByRole('dialog')).not.toBeInTheDocument()

    mockSpeech.listening = false
    mockSpeech.transcript = 'what is bihu'
    rerender(<VoiceAssistantButton touristId={1} />)
    await findByText(/harvest festival/)
  })

  it('stops auto-starting when the browser denies the microphone, instead of retry-looping', async () => {
    mock.onPost('/tourists/1/copilot/ask').reply(200, { answer: 'ok' })
    mockSpeech.error = 'not-allowed'
    const { rerender } = render(<VoiceAssistantButton touristId={1} />)
    // One attempt is unavoidable (the refusal only arrives in response to
    // it) -- the point is that it never becomes a retry loop.
    await waitFor(() => expect(mockSpeech.start).toHaveBeenCalledTimes(1))
    for (let i = 0; i < 5; i++) rerender(<VoiceAssistantButton touristId={1} />)
    await new Promise((r) => setTimeout(r, 50))
    expect(mockSpeech.start).toHaveBeenCalledTimes(1)
  })

  it('keeps hands-free on when the tourist simply said nothing (no-speech is not a failure)', async () => {
    mockSpeech.error = 'no-speech'
    render(<VoiceAssistantButton touristId={1} />)
    await waitFor(() => expect(mockSpeech.start).toHaveBeenCalled())
  })

  it('can be switched off, and the choice is remembered', async () => {
    const { getByLabelText, getByText, unmount } = render(<VoiceAssistantButton touristId={1} />)
    fireEvent.click(getByLabelText('Voice assistant'))
    fireEvent.click(getByText('♾️ Hands-free'))
    await waitFor(() => expect(getByText('👆 Tap to talk')).toBeInTheDocument())
    unmount()

    mockSpeech.start.mockClear()
    const second = render(<VoiceAssistantButton touristId={1} />)
    await new Promise((r) => setTimeout(r, 50))
    expect(mockSpeech.start).not.toHaveBeenCalled() // no auto-start on load
    // Tapping still works -- that's the whole point of "tap to talk".
    fireEvent.click(second.getByLabelText('Voice assistant'))
    expect(second.getByText('👆 Tap to talk')).toBeInTheDocument()
    expect(mockSpeech.start).toHaveBeenCalled()
  })
})

describe('VoiceAssistantButton UI', () => {
  it('shows the current language', () => {
    const { getByLabelText, getAllByText } = render(<VoiceAssistantButton touristId={1} lang="hi" />)
    fireEvent.click(getByLabelText('Voice assistant'))
    expect(getAllByText(/हिन्दी/).length).toBeGreaterThan(0)
  })

  it('shows a listening state with an animated meter', () => {
    mockSpeech.listening = true
    const { getByLabelText, getByText, container } = render(<VoiceAssistantButton touristId={1} />)
    fireEvent.click(getByLabelText('Voice assistant'))
    expect(getByText('Listening… speak now')).toBeInTheDocument()
    expect(container.querySelectorAll('.voice-bar').length).toBeGreaterThan(0)
  })

  it('shows a speaking state while the reply is read aloud', async () => {
    mock.onPost('/tourists/1/copilot/ask').reply(200, { answer: 'Kaziranga is 200 km away.' })
    // speak() resolves only when we let it, so the speaking state is observable.
    let finishSpeaking
    speak.mockImplementationOnce(() => new Promise((res) => { finishSpeaking = res }))

    const { getByLabelText, findByText, rerender } = render(<VoiceAssistantButton touristId={1} />)
    fireEvent.click(getByLabelText('Voice assistant'))
    mockSpeech.listening = false
    mockSpeech.transcript = 'how far is kaziranga'
    rerender(<VoiceAssistantButton touristId={1} />)

    await findByText('Speaking…')
    finishSpeaking()
    await waitFor(() => expect(document.body.textContent).not.toContain('Speaking…'))
  })

  it('shows the live transcript while the tourist is still talking', () => {
    mockSpeech.listening = true
    mockSpeech.transcript = 'where is the nearest'
    const { getByLabelText, getByText } = render(<VoiceAssistantButton touristId={1} />)
    fireEvent.click(getByLabelText('Voice assistant'))
    expect(getByText('where is the nearest')).toBeInTheDocument()
  })

  it('suggested commands are tappable and send the question', async () => {
    mock.onPost('/tourists/1/copilot/ask').reply(200, { answer: 'City Hospital, 1 km away.' })
    const { getByLabelText, getByText, findByText } = render(<VoiceAssistantButton touristId={1} />)
    fireEvent.click(getByLabelText('Voice assistant'))
    fireEvent.click(getByText('Find a cab.'))
    await findByText(/City Hospital/)
    expect(JSON.parse(mock.history.post[0].data).question).toBe('Find a cab.')
  })

  it('shows the transcript and the answer together as a conversation', async () => {
    mock.onPost('/tourists/1/copilot/ask').reply(200, { answer: 'Bihu is a harvest festival.' })
    const { getByLabelText, findByText, getByText, rerender } = render(<VoiceAssistantButton touristId={1} />)
    fireEvent.click(getByLabelText('Voice assistant'))
    mockSpeech.listening = false
    mockSpeech.transcript = 'what is bihu'
    rerender(<VoiceAssistantButton touristId={1} />)

    await findByText(/harvest festival/)
    expect(getByText('what is bihu')).toBeInTheDocument() // transcript kept alongside
  })
})
