import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, fireEvent, act } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import '../i18n' // initializes i18next so t() resolves real strings, not raw keys
import api from '../api'
import CopilotChat from './CopilotChat'

const mock = new MockAdapter(api)

// jsdom has no SpeechRecognition/SpeechSynthesis -- stub the hook/service
// this component uses so the mic button and voice-reply toggle can be
// exercised without a real browser speech engine.
let mockSpeechState
vi.mock('../hooks/useSpeechRecognition', () => ({
  default: () => mockSpeechState,
}))
const speakMock = vi.fn().mockResolvedValue()
vi.mock('../lib/voiceService', () => ({
  speak: (...args) => speakMock(...args),
  stopSpeaking: vi.fn(),
  speechSynthesisSupported: () => true,
}))

beforeEach(() => {
  mock.reset()
  speakMock.mockClear()
  mockSpeechState = {
    supported: true, listening: false, transcript: '', error: null,
    start: vi.fn(), stop: vi.fn(), reset: vi.fn(),
  }
})

describe('CopilotChat', () => {
  it('is closed by default', () => {
    const { queryByPlaceholderText } = render(<CopilotChat endpoint="/copilot/ask" />)
    expect(queryByPlaceholderText(/Ask a question/)).not.toBeInTheDocument()
  })

  it('opens and shows suggestion chips', () => {
    const { getByText } = render(<CopilotChat endpoint="/copilot/ask" suggestions={['How many alerts?']} />)
    fireEvent.click(getByText('🤖'))
    expect(getByText('How many alerts?')).toBeInTheDocument()
  })

  it('clicking a suggestion sends it and shows the answer', async () => {
    mock.onPost('/copilot/ask').reply(200, { answer: 'There are 3 active alerts.', handled: true })
    const { getByText, findByText } = render(<CopilotChat endpoint="/copilot/ask" suggestions={['How many alerts?']} />)
    fireEvent.click(getByText('🤖'))
    fireEvent.click(getByText('How many alerts?'))
    await findByText('There are 3 active alerts.')
  })

  it('typing and submitting a question works', async () => {
    mock.onPost('/copilot/ask').reply(200, { answer: 'Answer text.', handled: true })
    const { getByText, getByPlaceholderText, findByText } = render(<CopilotChat endpoint="/copilot/ask" />)
    fireEvent.click(getByText('🤖'))
    fireEvent.change(getByPlaceholderText(/Ask a question/), { target: { value: 'hello?' } })
    fireEvent.submit(getByPlaceholderText(/Ask a question/).closest('form'))
    await findByText('hello?')
    await findByText('Answer text.')
  })

  it('shows a fallback message on request failure', async () => {
    mock.onPost('/copilot/ask').reply(500)
    const { getByText, getByPlaceholderText, findByText } = render(<CopilotChat endpoint="/copilot/ask" />)
    fireEvent.click(getByText('🤖'))
    fireEvent.change(getByPlaceholderText(/Ask a question/), { target: { value: 'hi' } })
    fireEvent.submit(getByPlaceholderText(/Ask a question/).closest('form'))
    await findByText(/could not process/)
  })

  it('closes when the overlay is clicked', () => {
    const { getByText, queryByPlaceholderText } = render(<CopilotChat endpoint="/copilot/ask" />)
    fireEvent.click(getByText('🤖'))
    fireEvent.click(getByText('✕'))
    expect(queryByPlaceholderText(/Ask a question/)).not.toBeInTheDocument()
  })

  it('shows the mic button and starts listening on click', () => {
    const { getByText, getByTitle } = render(<CopilotChat endpoint="/copilot/ask" />)
    fireEvent.click(getByText('🤖'))
    fireEvent.click(getByTitle('Ask by voice'))
    expect(mockSpeechState.start).toHaveBeenCalled()
  })

  it('auto-submits once a voice transcript is captured', async () => {
    mock.onPost('/copilot/ask').reply(200, { answer: 'Voice answer.', handled: true })
    const { getByText, findByText, rerender } = render(<CopilotChat endpoint="/copilot/ask" />)
    fireEvent.click(getByText('🤖'))

    mockSpeechState = { ...mockSpeechState, listening: false, transcript: 'nearest hospital?' }
    rerender(<CopilotChat endpoint="/copilot/ask" />)

    await findByText('nearest hospital?')
    await findByText('Voice answer.')
  })

  it('speaks the reply aloud only when the speaker toggle is on', async () => {
    mock.onPost('/copilot/ask').reply(200, { answer: 'Spoken answer.', handled: true })
    const { getByText, getByPlaceholderText, findByText, getByTitle } = render(
      <CopilotChat endpoint="/copilot/ask" lang="en" />
    )
    fireEvent.click(getByText('🤖'))
    fireEvent.change(getByPlaceholderText(/Ask a question/), { target: { value: 'hi' } })
    fireEvent.submit(getByPlaceholderText(/Ask a question/).closest('form'))
    await findByText('Spoken answer.')
    expect(speakMock).not.toHaveBeenCalled() // off by default

    fireEvent.click(getByTitle('Voice replies off'))
    fireEvent.change(getByPlaceholderText(/Ask a question/), { target: { value: 'hi again' } })
    fireEvent.submit(getByPlaceholderText(/Ask a question/).closest('form'))
    await act(async () => {})
    expect(speakMock).toHaveBeenCalledWith('Spoken answer.', 'en')
  })
})
