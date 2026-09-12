import { describe, it, expect, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import api from '../api'
import DispatchPanel from './DispatchPanel'

const mock = new MockAdapter(api)

const candidates = [
  { unit_id: 1, name: 'Unit Alpha', unit_type: 'police', station: 'Central PS',
    distance_km: 0.5, eta_min: 1.0, available: true },
  { unit_id: 2, name: 'Ambulance 1', unit_type: 'ambulance', station: 'City Hospital',
    distance_km: 2.1, eta_min: 4.2, available: true },
]

beforeEach(() => mock.reset())

describe('DispatchPanel', () => {
  it('shows a loading state before the response arrives', () => {
    mock.onGet('/incidents/5/dispatch-candidates').reply(200, candidates)
    const { getByText } = render(<DispatchPanel incidentId={5} />)
    expect(getByText(/Loading candidates/)).toBeInTheDocument()
  })

  it('renders the top pick and backups with distance/ETA', async () => {
    mock.onGet('/incidents/5/dispatch-candidates').reply(200, candidates)
    const { getByText, findByText } = render(<DispatchPanel incidentId={5} />)

    await findByText('Unit Alpha')
    expect(getByText('TOP PICK')).toBeInTheDocument()
    expect(getByText('Ambulance 1')).toBeInTheDocument()
    expect(getByText(/0.5 km/)).toBeInTheDocument()
    expect(getByText(/2.1 km/)).toBeInTheDocument()
  })

  it('shows an empty state when no units are available', async () => {
    mock.onGet('/incidents/5/dispatch-candidates').reply(200, [])
    const { findByText } = render(<DispatchPanel incidentId={5} />)
    await findByText(/No available units nearby/)
  })

  it('surfaces an error instead of crashing when the request fails', async () => {
    mock.onGet('/incidents/5/dispatch-candidates').reply(500)
    const { findByText } = render(<DispatchPanel incidentId={5} />)
    await findByText(/Could not load dispatch candidates/)
  })

  it('refetches when the incidentId prop changes', async () => {
    mock.onGet('/incidents/5/dispatch-candidates').reply(200, candidates)
    mock.onGet('/incidents/6/dispatch-candidates').reply(200, [])
    const { rerender, findByText } = render(<DispatchPanel incidentId={5} />)
    await findByText('Unit Alpha')

    rerender(<DispatchPanel incidentId={6} />)
    await findByText(/No available units nearby/)
  })
})
