import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { useState } from 'react'

// api.js is a configured axios instance; stub it so no network is touched.
// refreshAccessToken/setAccessToken are also mocked here since AuthProvider
// calls refreshAccessToken() on mount to re-derive the in-memory access
// token from the httpOnly refresh-token cookie.
vi.mock('./api', () => ({
  default: { post: vi.fn() },
  refreshAccessToken: vi.fn(),
  setAccessToken: vi.fn(),
}))

import api, { refreshAccessToken } from './api'
import { AuthProvider, useAuth } from './auth.jsx'

function Probe() {
  const { user, ready, login, logout } = useAuth()
  const [error, setError] = useState(null)
  // Swallow the rejection here the way a real login form would, so a failed
  // login is asserted on rather than surfacing as an unhandled rejection.
  const doLogin = () => login('admin@test.gov', 'pw').catch((e) => setError(e.message))
  return (
    <div>
      <span data-testid="who">{user ? `${user.role}:${user.full_name}` : 'anonymous'}</span>
      <span data-testid="ready">{ready ? 'ready' : 'loading'}</span>
      <span data-testid="error">{error || ''}</span>
      <button onClick={doLogin}>login</button>
      <button onClick={logout}>logout</button>
    </div>
  )
}

const renderProbe = () => render(<AuthProvider><Probe /></AuthProvider>)

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
  refreshAccessToken.mockResolvedValue('tok')
})

describe('AuthProvider', () => {
  it('starts anonymous with empty storage and becomes ready with no refresh attempt', async () => {
    renderProbe()
    await act(async () => {})
    expect(screen.getByTestId('who')).toHaveTextContent('anonymous')
    expect(screen.getByTestId('ready')).toHaveTextContent('ready')
    expect(refreshAccessToken).not.toHaveBeenCalled()
  })

  it('rehydrates a session from localStorage after a successful silent refresh', async () => {
    localStorage.setItem('user', JSON.stringify({ role: 'admin', full_name: 'Officer' }))
    renderProbe()
    await act(async () => {})
    expect(refreshAccessToken).toHaveBeenCalled()
    expect(screen.getByTestId('who')).toHaveTextContent('admin:Officer')
    expect(screen.getByTestId('ready')).toHaveTextContent('ready')
  })

  it('drops a stale rehydrated user when the silent refresh fails', async () => {
    localStorage.setItem('user', JSON.stringify({ role: 'admin', full_name: 'Officer' }))
    refreshAccessToken.mockRejectedValue(new Error('refresh token expired'))
    renderProbe()
    await act(async () => {})
    expect(screen.getByTestId('who')).toHaveTextContent('anonymous')
    expect(localStorage.getItem('user')).toBeNull()
  })

  it('stores only the non-secret user object on login, never a token', async () => {
    api.post.mockResolvedValue({
      data: { access_token: 'tok123', refresh_token: 'refresh123', role: 'admin', tourist_id: null, full_name: 'Officer' },
    })
    renderProbe()
    await act(async () => { screen.getByText('login').click() })

    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('refreshToken')).toBeNull()
    expect(JSON.parse(localStorage.getItem('user')).role).toBe('admin')
    expect(screen.getByTestId('who')).toHaveTextContent('admin:Officer')
  })

  it('sends credentials as form-encoded fields (OAuth2 password flow)', async () => {
    api.post.mockResolvedValue({
      data: { access_token: 't', refresh_token: 'rt', role: 'tourist', tourist_id: 3, full_name: 'Aarav' },
    })
    renderProbe()
    await act(async () => { screen.getByText('login').click() })

    const [path, body] = api.post.mock.calls[0]
    expect(path).toBe('/auth/login')
    // The backend expects the email in the OAuth2 `username` field.
    expect(body.get('username')).toBe('admin@test.gov')
    expect(body.get('password')).toBe('pw')
  })

  it('keeps the tourist_id so the app can scope requests', async () => {
    api.post.mockResolvedValue({
      data: { access_token: 't', refresh_token: 'rt', role: 'tourist', tourist_id: 3, full_name: 'Aarav' },
    })
    renderProbe()
    await act(async () => { screen.getByText('login').click() })
    expect(JSON.parse(localStorage.getItem('user')).tourist_id).toBe(3)
  })

  it('clears local state on logout', async () => {
    api.post.mockResolvedValue({
      data: { access_token: 't', refresh_token: 'rt', role: 'admin', tourist_id: null, full_name: 'Officer' },
    })
    renderProbe()
    await act(async () => { screen.getByText('login').click() })
    await act(async () => { screen.getByText('logout').click() })

    expect(localStorage.getItem('user')).toBeNull()
    expect(screen.getByTestId('who')).toHaveTextContent('anonymous')
  })

  it('logout revokes the refresh token server-side via the httpOnly cookie (no body needed)', async () => {
    api.post.mockResolvedValue({
      data: { access_token: 't', refresh_token: 'rt-to-revoke', role: 'admin', tourist_id: null, full_name: 'Officer' },
    })
    renderProbe()
    await act(async () => { screen.getByText('login').click() })
    api.post.mockResolvedValue({})  // the /auth/logout call itself
    await act(async () => { screen.getByText('logout').click() })

    expect(api.post).toHaveBeenCalledWith('/auth/logout', {})
  })

  it('logout clears local state even if the revoke call fails', async () => {
    api.post.mockResolvedValueOnce({
      data: { access_token: 't', refresh_token: 'rt', role: 'admin', tourist_id: null, full_name: 'Officer' },
    })
    renderProbe()
    await act(async () => { screen.getByText('login').click() })
    api.post.mockRejectedValueOnce(new Error('network down'))
    await act(async () => { screen.getByText('logout').click() })

    expect(screen.getByTestId('who')).toHaveTextContent('anonymous')
  })

  it('leaves no session behind when login fails', async () => {
    api.post.mockRejectedValue(new Error('401'))
    renderProbe()
    await act(async () => { screen.getByText('login').click() })

    expect(localStorage.getItem('user')).toBeNull()
    expect(screen.getByTestId('who')).toHaveTextContent('anonymous')
    expect(screen.getByTestId('error')).toHaveTextContent('401')
  })
})
