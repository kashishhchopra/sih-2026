import { describe, it, expect, beforeEach } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import api from '../api'
import SafetyPassportCard from './SafetyPassportCard'

const mock = new MockAdapter(api)

const passport = {
  digital_id: 'STS-ABC123', preferred_language: 'Hindi', safety_score: 82,
  current_status: 'active',
  device: { device_id: 'BAND-1', battery_pct: 78, is_online: true },
  emergency_contacts: [{ name: 'Kin', phone: '+91-1', relation: 'family' }],
  qr_png_base64: 'data:image/png;base64,abc',
}

beforeEach(() => mock.reset())

describe('SafetyPassportCard', () => {
  it('is collapsed by default and does not fetch', () => {
    const { queryByAltText } = render(<SafetyPassportCard touristId={1} />)
    expect(queryByAltText(/QR code/)).not.toBeInTheDocument()
  })

  it('fetches and shows the passport when opened', async () => {
    mock.onGet('/tourists/1/passport').reply(200, passport)
    const { getByText, findByText } = render(<SafetyPassportCard touristId={1} />)
    fireEvent.click(getByText(/Digital Safety Passport/))
    await findByText('STS-ABC123')
    expect(await findByText(/Smart Band \(78%, online\)/)).toBeInTheDocument()
  })

  it('shows "none linked" when no device is present', async () => {
    mock.onGet('/tourists/1/passport').reply(200, { ...passport, device: null })
    const { getByText, findByText } = render(<SafetyPassportCard touristId={1} />)
    fireEvent.click(getByText(/Digital Safety Passport/))
    await findByText(/none linked/)
  })
})
