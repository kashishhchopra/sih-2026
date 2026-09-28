import { describe, it, expect, beforeEach } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import '../i18n' // initializes i18next so t() resolves real strings, not raw keys
import api from '../api'
import SafetyCardPanel from './SafetyCardPanel'

const mock = new MockAdapter(api)

const card = {
  digital_id: 'STS-ABC', nearest_hospital: { name: 'City Hospital', distance_km: 1.2, phone: '102' },
  nearest_police: { name: 'Central PS', distance_km: 0.8, phone: '100' },
  emergency_numbers: { all_in_one: '112', police: '100' },
  note: 'Works offline once loaded.',
}

beforeEach(() => mock.reset())

describe('SafetyCardPanel', () => {
  it('is collapsed by default and does not fetch', () => {
    const { queryByText } = render(<SafetyCardPanel touristId={1} />)
    expect(queryByText('City Hospital')).not.toBeInTheDocument()
  })

  it('fetches and shows the card when opened', async () => {
    mock.onGet('/tourists/1/safety-card').reply(200, card)
    const { getByText, findByText } = render(<SafetyCardPanel touristId={1} />)
    fireEvent.click(getByText(/Offline Safety Card/))
    await findByText(/City Hospital/)
    await findByText(/Central PS/)
    await findByText('112')
  })
})
