import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, fireEvent, waitFor } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import '../i18n' // initializes i18next so t() resolves real strings, not raw keys
import api from '../api'
import TranslateCard from './TranslateCard'

vi.mock('../lib/voiceService.js', () => ({
  speak: vi.fn(),
  speechSynthesisSupported: () => false,
}))

const mock = new MockAdapter(api)

beforeEach(() => mock.reset())

describe('TranslateCard', () => {
  it('is collapsed by default', () => {
    const { queryByText } = render(<TranslateCard />)
    expect(queryByText('Translate')).not.toBeInTheDocument()
  })

  it('loads languages and phrases on open, translates a phrase', async () => {
    mock.onGet('/translate/languages').reply(200, { en: 'English', hi: 'Hindi' })
    mock.onGet('/translate/phrases').reply(200, ['need_doctor', 'call_police'])
    mock.onPost('/translate/phrase').reply(200, { text: 'मुझे डॉक्टर चाहिए।', demo: false })

    const { getByText, findByText } = render(<TranslateCard />)
    fireEvent.click(getByText('🌐 Translate a phrase'))
    await findByText('need doctor')
    fireEvent.click(getByText('need doctor'))
    await findByText('मुझे डॉक्टर चाहिए।')
    expect(mock.history.post[0].data).toContain('"phrase_id":"need_doctor"')
  })

  it('translates free text and shows the demo-mode note', async () => {
    mock.onGet('/translate/languages').reply(200, { en: 'English', fr: 'French' })
    mock.onGet('/translate/phrases').reply(200, [])
    mock.onPost('/translate/text').reply(200, {
      text: 'hello', demo: true, note: 'Live translation is unavailable in demo mode; showing the original text.',
    })

    const { getByText, getByPlaceholderText, findByText } = render(<TranslateCard />)
    fireEvent.click(getByText('🌐 Translate a phrase'))
    await waitFor(() => expect(mock.history.get).toHaveLength(2))
    fireEvent.change(getByPlaceholderText('Or type something to translate…'), { target: { value: 'hello' } })
    fireEvent.click(getByText('Go'))
    await findByText(/Demo mode/)
  })

  it('shows an error if the service is unavailable', async () => {
    mock.onGet('/translate/languages').reply(500)
    mock.onGet('/translate/phrases').reply(500)
    const { getByText, findByText } = render(<TranslateCard />)
    fireEvent.click(getByText('🌐 Translate a phrase'))
    await findByText('Translation service is unavailable right now.')
  })
})
