import { describe, it, expect, beforeEach } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import api from '../api'
import TouristIdScanner from './TouristIdScanner'

const mock = new MockAdapter(api)

beforeEach(() => mock.reset())

describe('TouristIdScanner', () => {
  it('manual lookup shows a verified tourist', async () => {
    mock.onPost('/tourist-id/scan').reply(200, {
      verification_status: 'verified', digital_id: 'STS-ABC123', full_name: 'Kashish Chopra',
      photo: null, current_zone: { id: 1, name: 'Old Market High-Risk Zone', risk_level: 'high' },
      assigned_station: { id: 1, name: 'Market PS', phone: '100' },
      trip_status: 'active', emergency_contacts: [{ name: 'Kin', phone: '+91-1', relation: 'family' }],
      active_incidents: [],
    })
    const { getByPlaceholderText, getByText, findByText } = render(<TouristIdScanner />)
    fireEvent.change(getByPlaceholderText(/STS-/), { target: { value: 'STS-ABC123' } })
    fireEvent.click(getByText('Verify'))

    await findByText(/TOURIST VERIFIED/)
    await findByText('Kashish Chopra')
    await findByText('Market PS')
  })

  it('shows invalid state for an unknown ID', async () => {
    mock.onPost('/tourist-id/scan').reply(200, {
      verification_status: 'not_found', reason: 'No tourist matches that ID or QR code.',
    })
    const { getByPlaceholderText, getByText, findByText } = render(<TouristIdScanner />)
    fireEvent.change(getByPlaceholderText(/STS-/), { target: { value: 'STS-NOPE' } })
    fireEvent.click(getByText('Verify'))

    await findByText(/INVALID TOURIST ID/)
    await findByText(/No tourist matches/)
  })

  it('shows expired state', async () => {
    mock.onPost('/tourist-id/scan').reply(200, {
      verification_status: 'expired', reason: "This tourist's trip has ended.",
    })
    const { getByPlaceholderText, getByText, findByText } = render(<TouristIdScanner />)
    fireEvent.change(getByPlaceholderText(/STS-/), { target: { value: 'STS-OLD' } })
    fireEvent.click(getByText('Verify'))

    await findByText(/TOURIST ID EXPIRED/)
  })

  it('renders host-provided actions only for a verified result', async () => {
    mock.onPost('/tourist-id/scan').reply(200, {
      verification_status: 'verified', digital_id: 'STS-ABC123', full_name: 'Kashish Chopra',
    })
    const { getByPlaceholderText, getByText, findByText } = render(
      <TouristIdScanner renderActions={() => <button>Report Incident</button>} />
    )
    fireEvent.change(getByPlaceholderText(/STS-/), { target: { value: 'STS-ABC123' } })
    fireEvent.click(getByText('Verify'))

    await findByText('Report Incident')
  })

  it('"Scan another" resets back to manual entry', async () => {
    mock.onPost('/tourist-id/scan').reply(200, {
      verification_status: 'not_found', reason: 'x',
    })
    const { getByPlaceholderText, getByText, findByText } = render(<TouristIdScanner />)
    fireEvent.change(getByPlaceholderText(/STS-/), { target: { value: 'STS-NOPE' } })
    fireEvent.click(getByText('Verify'))
    await findByText(/INVALID TOURIST ID/)

    fireEvent.click(getByText(/Scan another/))
    expect(getByPlaceholderText(/STS-/).value).toBe('')
  })
})
