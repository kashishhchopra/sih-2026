import { describe, it, expect, beforeEach } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import api from '../api'
import PrivacyCard from './PrivacyCard'

const mock = new MockAdapter(api)

const report = {
  tracking_enabled: true, data_retention_days: 90, preferred_language: 'en',
  location_pings_stored: 42, auto_purge_at: '2026-06-01T00:00:00',
}

beforeEach(() => mock.reset())

describe('PrivacyCard', () => {
  it('renders nothing until the report loads', () => {
    mock.onGet('/tourists/1/privacy').reply(200, report)
    const { container } = render(<PrivacyCard touristId={1} />)
    expect(container.firstChild).toBeNull()
  })

  it('shows the retention and ping-count report', async () => {
    mock.onGet('/tourists/1/privacy').reply(200, report)
    const { findByText } = render(<PrivacyCard touristId={1} />)
    await findByText('42')
  })

  it('deleting location history calls the purge endpoint and shows the count', async () => {
    mock.onGet('/tourists/1/privacy').reply(200, report)
    mock.onDelete('/tourists/1/location-history').reply(200, { tourist_id: 1, pings_deleted: 42 })
    window.confirm = () => true

    const { findByText } = render(<PrivacyCard touristId={1} />)
    fireEvent.click(await findByText(/Delete my location history/))
    await findByText(/42 location record\(s\) deleted/)
  })

  it('does not delete when the user cancels the confirmation', async () => {
    mock.onGet('/tourists/1/privacy').reply(200, report)
    window.confirm = () => false

    const { findByText, queryByText } = render(<PrivacyCard touristId={1} />)
    fireEvent.click(await findByText(/Delete my location history/))
    expect(queryByText(/location record\(s\) deleted/)).not.toBeInTheDocument()
  })
})
