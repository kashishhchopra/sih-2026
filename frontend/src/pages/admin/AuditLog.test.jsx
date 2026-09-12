import { describe, it, beforeEach } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import api from '../../api'
import AuditLog from './AuditLog'

const mock = new MockAdapter(api)

beforeEach(() => mock.reset())

describe('AuditLog page', () => {
  it('renders the audit log table', async () => {
    mock.onGet('/audit-log?limit=200').reply(200, [
      { timestamp: '2026-01-01T00:00:00', action: 'login', actor: 'admin@test.gov',
        target: '', ip: '127.0.0.1', outcome: 'success', detail: '' },
    ])
    mock.onGet('/anchors').reply(200, [])
    mock.onGet('/disasters').reply(200, [])
    const { findByText } = render(<AuditLog />)
    await findByText('admin@test.gov')
  })

  it('publishing an anchor calls the endpoint and refreshes the list', async () => {
    mock.onGet('/audit-log?limit=200').reply(200, [])
    mock.onGet('/disasters').reply(200, [])
    mock.onGet('/anchors').replyOnce(200, [])
    mock.onPost('/anchors').reply(201, { id: 1, root_hash: 'a'.repeat(64), tourist_count: 2,
      block_count: 4, anchor_target: 'local', external_ref: 'abc123', created_at: '2026-01-01T00:00:00' })
    mock.onGet('/anchors').reply(200, [
      { id: 1, root_hash: 'a'.repeat(64), tourist_count: 2, block_count: 4,
        anchor_target: 'local', external_ref: 'abc123', created_at: '2026-01-01T00:00:00' },
    ])

    const { findByText } = render(<AuditLog />)
    fireEvent.click(await findByText(/Anchor now/))
    await findByText(/2 tourists/)
  })

  it('verifying an anchor shows the result', async () => {
    mock.onGet('/audit-log?limit=200').reply(200, [])
    mock.onGet('/disasters').reply(200, [])
    mock.onGet('/anchors').reply(200, [
      { id: 1, root_hash: 'a'.repeat(64), tourist_count: 2, block_count: 4,
        anchor_target: 'local', external_ref: 'abc123', created_at: '2026-01-01T00:00:00' },
    ])
    mock.onGet('/anchors/1/verify').reply(200, { verified: true, detail: 'Ledger entry matches.' })

    const { findByText } = render(<AuditLog />)
    fireEvent.click(await findByText('Verify'))
    await findByText(/Ledger entry matches/)
  })

  it('shows active disaster advisories', async () => {
    mock.onGet('/audit-log?limit=200').reply(200, [])
    mock.onGet('/anchors').reply(200, [])
    mock.onGet('/disasters').reply(200, [
      { id: 1, zone_id: 1, hazard_type: 'flood', severity: 'high', message: 'Flood warning.',
        source: 'simulated', active: true, issued_at: '2026-01-01T00:00:00', expires_at: null },
    ])

    const { findByText } = render(<AuditLog />)
    await findByText(/Flood warning/)
  })
})
