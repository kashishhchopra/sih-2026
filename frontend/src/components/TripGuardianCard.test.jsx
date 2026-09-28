import { describe, it, beforeEach } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import api from '../api'
import TripGuardianCard from './TripGuardianCard'

const mock = new MockAdapter(api)

beforeEach(() => mock.reset())

describe('TripGuardianCard', () => {
  it('shows an empty state with no guardians', async () => {
    mock.onGet('/tourists/1/guardians').reply(200, [])
    const { findByText } = render(<TripGuardianCard touristId={1} />)
    await findByText(/No active guardians/)
  })

  it('lists active guardians with a share link', async () => {
    mock.onGet('/tourists/1/guardians').reply(200, [
      { id: 1, token: 'tok123', guardian_name: 'Mom', guardian_contact: '', revoked: false, created_at: '2026-01-01T00:00:00' },
    ])
    const { findByText, findByDisplayValue } = render(<TripGuardianCard touristId={1} />)
    await findByText('Mom')
    await findByDisplayValue(/\/guardian\/tok123$/)
  })

  it('creates a new guardian share link', async () => {
    mock.onGet('/tourists/1/guardians').replyOnce(200, [])
    mock.onPost('/tourists/1/guardians').reply(201, {
      id: 2, token: 'newtok', guardian_name: 'Dad', guardian_contact: '', revoked: false, created_at: '2026-01-01T00:00:00',
    })
    mock.onGet('/tourists/1/guardians').reply(200, [
      { id: 2, token: 'newtok', guardian_name: 'Dad', guardian_contact: '', revoked: false, created_at: '2026-01-01T00:00:00' },
    ])
    const { getByPlaceholderText, getByText, findByText } = render(<TripGuardianCard touristId={1} />)
    await findByText(/No active guardians/)
    fireEvent.change(getByPlaceholderText(/Guardian's name/), { target: { value: 'Dad' } })
    fireEvent.click(getByText(/Create share link/))
    await findByText('Dad')
  })

  it('revoking a guardian removes it from the active list', async () => {
    mock.onGet('/tourists/1/guardians').replyOnce(200, [
      { id: 1, token: 'tok123', guardian_name: 'Mom', guardian_contact: '', revoked: false, created_at: '2026-01-01T00:00:00' },
    ])
    mock.onPost('/tourists/1/guardians/1/revoke').reply(200, {})
    mock.onGet('/tourists/1/guardians').reply(200, [
      { id: 1, token: 'tok123', guardian_name: 'Mom', guardian_contact: '', revoked: true, created_at: '2026-01-01T00:00:00' },
    ])
    const { findByText } = render(<TripGuardianCard touristId={1} />)
    fireEvent.click(await findByText('revoke'))
    await findByText(/No active guardians/)
  })
})
