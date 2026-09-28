import { describe, it, expect, beforeEach } from 'vitest'
import { render, fireEvent, waitFor } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import '../i18n' // initializes i18next so t() resolves real strings, not raw keys
import api from '../api'
import ItineraryUploadCard from './ItineraryUploadCard'

const mock = new MockAdapter(api)

beforeEach(() => mock.reset())

const extracted = {
  trip_start: '2026-09-01', trip_end: '2026-09-10',
  destinations: [{ name: 'Delhi', lat: 28.6139, lng: 77.209 }, { name: 'Agra', lat: 27.1767, lng: 78.0081 }],
  hotels: [{ name: 'Taj Hotel', check_in: true, check_out: false }],
  transport: [{ detail: 'Flight AI-101' }],
  activities: [],
}

function makeFile(name = 'trip.txt', content = 'Delhi -> Agra') {
  return new File([content], name, { type: 'text/plain' })
}

describe('ItineraryUploadCard', () => {
  it('is collapsed by default', () => {
    const { queryByText } = render(<ItineraryUploadCard touristId={1} />)
    expect(queryByText('Upload Itinerary Document')).not.toBeInTheDocument()
  })

  it('uploads a file and shows extracted destinations for review', async () => {
    mock.onPost('/tourists/1/itinerary-documents').reply(201, {
      id: 5, tourist_id: 1, filename: 'trip.txt', content_type: 'text/plain',
      uploaded_at: '2026-01-01T00:00:00', status: 'extracted', error: '',
      extracted, confirmed: false, confirmed_at: null,
    })
    const { getByText, container, findByDisplayValue } = render(<ItineraryUploadCard touristId={1} />)
    fireEvent.click(getByText('📄 Upload My Itinerary'))
    const input = container.querySelector('input[type="file"]')
    fireEvent.change(input, { target: { files: [makeFile()] } })

    await findByDisplayValue('Delhi')
    await findByDisplayValue('Agra')
    expect(getByText('🏨 Taj Hotel')).toBeInTheDocument()
    expect(getByText('🚄 Flight AI-101')).toBeInTheDocument()
  })

  it('shows the extraction error but still lets the tourist add destinations manually', async () => {
    mock.onPost('/tourists/1/itinerary-documents').reply(201, {
      id: 6, tourist_id: 1, filename: 'scan.jpg', content_type: 'image/jpeg',
      uploaded_at: '2026-01-01T00:00:00', status: 'failed',
      error: 'OCR is not available in this deployment.',
      extracted: { trip_start: null, trip_end: null, destinations: [], hotels: [], transport: [], activities: [] },
      confirmed: false, confirmed_at: null,
    })
    const { getByText, container, findByText } = render(<ItineraryUploadCard touristId={1} />)
    fireEvent.click(getByText('📄 Upload My Itinerary'))
    const input = container.querySelector('input[type="file"]')
    fireEvent.change(input, { target: { files: [makeFile('scan.jpg')] } })

    await findByText(/OCR is not available/)
    expect(getByText('+ Add destination')).toBeInTheDocument()
  })

  it('auto-locates destinations the parser could not place right after upload', async () => {
    mock.onPost('/tourists/1/itinerary-documents').reply(201, {
      id: 8, tourist_id: 1, filename: 'trip.txt', content_type: 'text/plain',
      uploaded_at: '2026-01-01T00:00:00', status: 'extracted', error: '',
      extracted: {
        trip_start: null, trip_end: null,
        destinations: [{ name: 'Kamakhya Temple' }], // no lat -- parser couldn't place it
        hotels: [], transport: [], activities: [],
      },
      confirmed: false, confirmed_at: null,
    })
    mock.onGet('/maps/geocode').reply(200, { lat: 26.1664, lng: 91.705, demo: true })
    mock.onPatch('/tourists/1/itinerary-documents/8').reply(200, {})
    mock.onPost('/tourists/1/itinerary-documents/8/confirm').reply(200, {})

    const { getByText, container, findByText, findByDisplayValue } = render(<ItineraryUploadCard touristId={1} />)
    fireEvent.click(getByText('📄 Upload My Itinerary'))
    const input = container.querySelector('input[type="file"]')
    fireEvent.change(input, { target: { files: [makeFile()] } })
    await findByDisplayValue('Kamakhya Temple')
    // Resolved automatically -- no manual tap needed.
    await findByText('📍✓')

    // Editing the name again invalidates that resolved location, and a
    // manual re-locate becomes available.
    fireEvent.change(container.querySelector('input.flex-1'), { target: { value: 'Somewhere Else' } })
    await findByText('📍 Locate')
    fireEvent.click(getByText('📍 Locate'))
    await findByText('📍✓')

    fireEvent.click(getByText('Confirm & Save Itinerary'))
    await waitFor(() => expect(getByText('✓ Itinerary saved')).toBeInTheDocument())
    expect(container.textContent).not.toMatch(/couldn't be placed on the map/)
  })

  it('warns after confirming when a destination genuinely cannot be located', async () => {
    mock.onPost('/tourists/1/itinerary-documents').reply(201, {
      id: 9, tourist_id: 1, filename: 'trip.txt', content_type: 'text/plain',
      uploaded_at: '2026-01-01T00:00:00', status: 'extracted', error: '',
      extracted: {
        trip_start: null, trip_end: null,
        destinations: [{ name: 'Nowhereville Xyzzy' }],
        hotels: [], transport: [], activities: [],
      },
      confirmed: false, confirmed_at: null,
    })
    mock.onGet('/maps/geocode').reply(200, { lat: null, lng: null, demo: true })
    mock.onPatch('/tourists/1/itinerary-documents/9').reply(200, {})
    mock.onPost('/tourists/1/itinerary-documents/9/confirm').reply(200, {})

    const { getByText, container, findByDisplayValue, findByText } = render(<ItineraryUploadCard touristId={1} />)
    fireEvent.click(getByText('📄 Upload My Itinerary'))
    const input = container.querySelector('input[type="file"]')
    fireEvent.change(input, { target: { files: [makeFile()] } })
    await findByDisplayValue('Nowhereville Xyzzy')
    await findByText('📍 Locate') // auto-locate ran and still couldn't place it

    fireEvent.click(getByText('Confirm & Save Itinerary'))
    await waitFor(() => expect(getByText('✓ Itinerary saved')).toBeInTheDocument())
    await findByText(/couldn't be placed on the map/)
  })

  it('editing and confirming saves the itinerary and calls onConfirmed', async () => {
    mock.onPost('/tourists/1/itinerary-documents').reply(201, {
      id: 7, tourist_id: 1, filename: 'trip.txt', content_type: 'text/plain',
      uploaded_at: '2026-01-01T00:00:00', status: 'extracted', error: '',
      extracted, confirmed: false, confirmed_at: null,
    })
    mock.onPatch('/tourists/1/itinerary-documents/7').reply(200, {})
    mock.onPost('/tourists/1/itinerary-documents/7/confirm').reply(200, {})

    let confirmedCalled = false
    const { getByText, container, findByDisplayValue } = render(
      <ItineraryUploadCard touristId={1} onConfirmed={() => { confirmedCalled = true }} />
    )
    fireEvent.click(getByText('📄 Upload My Itinerary'))
    const input = container.querySelector('input[type="file"]')
    fireEvent.change(input, { target: { files: [makeFile()] } })
    await findByDisplayValue('Delhi')

    fireEvent.click(getByText('Confirm & Save Itinerary'))
    await waitFor(() => expect(getByText('✓ Itinerary saved')).toBeInTheDocument())
    expect(confirmedCalled).toBe(true)
    expect(mock.history.patch).toHaveLength(1)
    expect(mock.history.post.some((r) => r.url === '/tourists/1/itinerary-documents/7/confirm')).toBe(true)
  })
})
