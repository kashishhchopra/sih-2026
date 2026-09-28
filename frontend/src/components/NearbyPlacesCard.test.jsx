import { describe, it, expect, beforeEach } from 'vitest'
import { render, fireEvent, waitFor } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import '../i18n' // initializes i18next so t() resolves real strings, not raw keys
import api from '../api'
import NearbyPlacesCard from './NearbyPlacesCard'

const mock = new MockAdapter(api)

beforeEach(() => mock.reset())

describe('NearbyPlacesCard', () => {
  it('is collapsed by default', () => {
    const { queryByText } = render(<NearbyPlacesCard touristId={1} />)
    expect(queryByText('Nearby')).not.toBeInTheDocument()
  })

  it('loads hospitals on open and shows distance + directions link', async () => {
    mock.onGet('/tourists/1/nearby?category=hospital').reply(200, [
      { name: 'City Hospital', category: 'hospital', distance_km: 1.2, phone: '108',
        source: 'osm', directions_url: 'https://www.google.com/maps/dir/?api=1&destination=1,2' },
    ])
    const { getByText, findByText } = render(<NearbyPlacesCard touristId={1} />)
    fireEvent.click(getByText('🗺️ Nearby Hospitals, Pharmacies & Transport'))
    await findByText('City Hospital')
    expect(getByText('1.2 km away')).toBeInTheDocument()
    expect(getByText('Directions').closest('a')).toHaveAttribute(
      'href', 'https://www.google.com/maps/dir/?api=1&destination=1,2')
  })

  it('switches category tabs and refetches', async () => {
    mock.onGet('/tourists/1/nearby?category=hospital').reply(200, [])
    mock.onGet('/tourists/1/nearby?category=pharmacy').reply(200, [
      { name: 'MedPlus', category: 'pharmacy', distance_km: 0.5, phone: '', source: 'manual',
        directions_url: 'https://www.google.com/maps/dir/?api=1&destination=3,4' },
    ])
    const { getByText, findByText } = render(<NearbyPlacesCard touristId={1} />)
    fireEvent.click(getByText('🗺️ Nearby Hospitals, Pharmacies & Transport'))
    await waitFor(() => expect(mock.history.get).toHaveLength(1))
    fireEvent.click(getByText('💊 Pharmacy'))
    await findByText('MedPlus')
  })

  it('shows an empty-state message when nothing is nearby', async () => {
    mock.onGet('/tourists/1/nearby?category=hospital').reply(200, [])
    const { getByText, findByText } = render(<NearbyPlacesCard touristId={1} />)
    fireEvent.click(getByText('🗺️ Nearby Hospitals, Pharmacies & Transport'))
    await findByText(/Nothing found nearby yet/)
  })

  it('shows an error message when the request fails', async () => {
    mock.onGet('/tourists/1/nearby?category=hospital').reply(500)
    const { getByText, findByText } = render(<NearbyPlacesCard touristId={1} />)
    fireEvent.click(getByText('🗺️ Nearby Hospitals, Pharmacies & Transport'))
    await findByText('Could not load nearby places right now.')
  })
})
