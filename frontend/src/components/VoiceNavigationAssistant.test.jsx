import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, fireEvent, waitFor } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import '../i18n' // initializes i18next so t() resolves real strings, not raw keys
import api from '../api'
import VoiceNavigationAssistant from './VoiceNavigationAssistant'

const mock = new MockAdapter(api)

vi.mock('../lib/voiceService.js', () => ({
  speak: vi.fn(() => Promise.resolve()),
  stopSpeaking: vi.fn(),
  speechSynthesisSupported: () => true,
}))

import { speak, stopSpeaking } from '../lib/voiceService.js'

beforeEach(() => {
  mock.reset()
  speak.mockClear()
  stopSpeaking.mockClear()
  localStorage.clear()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('VoiceNavigationAssistant', () => {
  it('shows an empty state when there is no destination', async () => {
    mock.onGet('/tourists/1/navigation').reply(200, { has_destination: false })
    const { findByText } = render(<VoiceNavigationAssistant touristId={1} />)
    await findByText(/No upcoming destination/)
  })

  it('shows the instruction and distance/ETA when guidance is available', async () => {
    mock.onGet('/tourists/1/navigation').reply(200, {
      has_destination: true, destination_name: 'Kamakhya Temple',
      distance_km: 1.4, eta_minutes: 6, demo: true, arrived: false,
      instruction: 'Head north-east for about 1.4 kilometres to reach Kamakhya Temple. Estimated time: about 6 minutes.',
    })
    const { findByText } = render(<VoiceNavigationAssistant touristId={1} />)
    await findByText(/Head north-east/)
    await findByText(/1.4 km · ETA ~6 min/)
  })

  it('defaults to voice off and does not speak until toggled on', async () => {
    mock.onGet('/tourists/1/navigation').reply(200, {
      has_destination: true, destination_name: 'Kamakhya Temple',
      distance_km: 1.4, eta_minutes: 6, demo: true, arrived: false,
      instruction: 'Head north-east...',
    })
    const { findByText, getByText } = render(<VoiceNavigationAssistant touristId={1} />)
    await findByText(/Head north-east/)
    expect(getByText('🔈 Voice: Off')).toBeInTheDocument()
    expect(speak).not.toHaveBeenCalled()
  })

  it('speaks the instruction once switched on, and stops speaking when switched off', async () => {
    mock.onGet('/tourists/1/navigation').reply(200, {
      has_destination: true, destination_name: 'Kamakhya Temple',
      distance_km: 1.4, eta_minutes: 6, demo: true, arrived: false,
      instruction: 'Head north-east...',
    })
    const { findByText, getByText } = render(<VoiceNavigationAssistant touristId={1} lang="hi" />)
    await findByText(/Head north-east/)

    fireEvent.click(getByText('🔈 Voice: Off'))
    await waitFor(() => expect(getByText('🔊 Voice: On')).toBeInTheDocument())
    await waitFor(() => expect(speak).toHaveBeenCalledWith('Head north-east...', 'hi'))

    fireEvent.click(getByText('🔊 Voice: On'))
    await waitFor(() => expect(stopSpeaking).toHaveBeenCalled())
  })

  it('remembers the on/off preference per tourist across remounts', async () => {
    mock.onGet('/tourists/1/navigation').reply(200, { has_destination: false })
    const { getByText, unmount } = render(<VoiceNavigationAssistant touristId={1} />)
    fireEvent.click(getByText('🔈 Voice: Off'))
    await waitFor(() => expect(getByText('🔊 Voice: On')).toBeInTheDocument())
    unmount()

    const { getByText: getByText2 } = render(<VoiceNavigationAssistant touristId={1} />)
    expect(getByText2('🔊 Voice: On')).toBeInTheDocument()
  })

  it('shows an error message if the guidance request fails', async () => {
    mock.onGet('/tourists/1/navigation').reply(500)
    const { findByText } = render(<VoiceNavigationAssistant touristId={1} />)
    await findByText('Navigation guidance is unavailable right now.')
  })
})
