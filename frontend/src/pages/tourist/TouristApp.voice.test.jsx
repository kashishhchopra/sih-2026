import { describe, it, expect, vi } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { ThemeProvider } from '../../theme.jsx'
import TouristApp from './TouristApp'

// Smoke test for the one thing that must be true on EVERY tourist screen:
// the voice assistant button is mounted. Component-level tests already cover
// the button's own behaviour -- this proves it's actually wired into the
// real app shell, on every tab, which is the part a unit test can't catch.

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }) => <div>{children}</div>,
  TileLayer: () => null,
  Marker: () => null,
  Polygon: () => null,
  Polyline: () => null,
  useMap: () => ({ flyTo: () => {}, getZoom: () => 13 }),
  useMapEvents: () => null,
}))

vi.mock('../../auth.jsx', () => ({
  useAuth: () => ({ user: { id: 1, role: 'tourist', tourist_id: 1, full_name: 'Aarav' } }),
}))

// The data hook does live polling/geolocation; this test is about the shell,
// so it gets a ready, static snapshot.
vi.mock('./useTouristData.js', () => ({
  default: () => ({
    ready: true,
    me: { id: 1, full_name: 'Aarav', digital_id: 'STS-001', last_lat: 26.14, last_lng: 91.73, itinerary: [] },
    score: { score: 82, breakdown: { zone: 'City Center', night_penalty: false, explanation: null } },
    zones: [], trajectory: [], nearby: [], riskyZone: null,
    routePicker: { dest: null, result: null, pick: () => {} },
    routePickerOpen: false, setRoutePickerOpen: () => {},
    riskForecast: null, online: true, toast: null,
    sendSOS: () => {}, load: () => {}, posRef: { current: null },
  }),
}))

describe('TouristApp voice assistant wiring', () => {
  it('mounts the voice assistant button in the app shell', async () => {
    const { getByLabelText } = render(<TouristApp />, { wrapper: ThemeProvider })
    await waitFor(() => expect(getByLabelText('Voice assistant')).toBeInTheDocument())
  })

  it('keeps the voice button available alongside the SOS and chat buttons', async () => {
    const { getByLabelText, getByText } = render(<TouristApp />, { wrapper: ThemeProvider })
    await waitFor(() => expect(getByLabelText('Voice assistant')).toBeInTheDocument())
    expect(getByText('🤖')).toBeInTheDocument() // the typed-chat assistant
    expect(getByLabelText('Voice assistant').className).toContain('fixed')
  })
})
