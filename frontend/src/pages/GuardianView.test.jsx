import { describe, it, beforeEach, vi } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import MockAdapter from 'axios-mock-adapter'
import api from '../api'
import GuardianView from './GuardianView'

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }) => <div>{children}</div>,
  TileLayer: () => null,
  Marker: () => null,
}))
vi.mock('../components/mapIcons', () => ({ touristIcon: () => ({}) }))

const mock = new MockAdapter(api)

function renderAt(token) {
  return render(
    <MemoryRouter initialEntries={[`/guardian/${token}`]}>
      <Routes>
        <Route path="/guardian/:token" element={<GuardianView />} />
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => mock.reset())

describe('GuardianView', () => {
  it('shows an error for an invalid or revoked link', async () => {
    mock.onGet('/guardian/bad-token').reply(404, { detail: 'This share link is invalid or has been revoked' })
    const { findByText } = renderAt('bad-token')
    await findByText(/invalid or has been revoked/)
  })

  it('shows live status for a valid link', async () => {
    mock.onGet('/guardian/good-token').reply(200, {
      guardian_name: 'Mom', tourist_name: 'Aarav Sharma', status: 'active',
      safety_score: 88, last_lat: 26.14, last_lng: 91.73,
      last_seen: '2026-01-01T10:00:00', trip_start: '2026-01-01T00:00:00',
      trip_end: '2026-01-10T00:00:00', trip_active: true,
    })
    const { findByText } = renderAt('good-token')
    await findByText('Aarav Sharma')
    await findByText(/88/)
  })

  it('shows an SOS banner when the tourist is in distress', async () => {
    mock.onGet('/guardian/good-token').reply(200, {
      guardian_name: 'Mom', tourist_name: 'Aarav Sharma', status: 'sos',
      safety_score: 20, last_lat: 26.14, last_lng: 91.73,
      last_seen: '2026-01-01T10:00:00', trip_start: '2026-01-01T00:00:00',
      trip_end: '2026-01-10T00:00:00', trip_active: true,
    })
    const { findByText } = renderAt('good-token')
    await findByText(/has triggered an SOS/)
  })
})
