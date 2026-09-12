import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import MockAdapter from 'axios-mock-adapter'
import api, { bare, getAccessToken, setAccessToken } from './api'

// `location.href = ...` isn't implemented by jsdom's Navigation and throws;
// stub it so the "give up and redirect" path can be exercised in tests.
beforeEach(() => {
  delete window.location
  window.location = { pathname: '/admin', href: '' }
})

const apiMock = new MockAdapter(api)
const bareMock = new MockAdapter(bare)

beforeEach(() => {
  localStorage.clear()
  setAccessToken(null)
  apiMock.reset()
  bareMock.reset()
})

afterEach(() => {
  apiMock.resetHandlers()
  bareMock.resetHandlers()
})

describe('api request interceptor', () => {
  it('attaches the bearer token when present', async () => {
    setAccessToken('abc123')
    apiMock.onGet('/whoami').reply((config) => {
      expect(config.headers.Authorization).toBe('Bearer abc123')
      return [200, { ok: true }]
    })
    await api.get('/whoami')
  })

  it('sends no Authorization header when logged out', async () => {
    apiMock.onGet('/whoami').reply((config) => {
      expect(config.headers.Authorization).toBeUndefined()
      return [200, {}]
    })
    await api.get('/whoami')
  })
})

describe('api response interceptor — refresh-on-401', () => {
  it('transparently retries the original request after a successful refresh', async () => {
    setAccessToken('expired')

    let calls = 0
    apiMock.onGet('/protected').reply(() => {
      calls += 1
      if (calls === 1) return [401, { detail: 'expired' }]
      return [200, { data: 'secret' }]
    })
    // The refresh token itself travels as an httpOnly cookie the test
    // environment doesn't model -- only the resulting access token matters.
    bareMock.onPost('/auth/refresh').reply(200, {
      access_token: 'fresh-token', refresh_token: 'fresh-refresh',
    })

    const res = await api.get('/protected')
    expect(res.data).toEqual({ data: 'secret' })
    expect(getAccessToken()).toBe('fresh-token')
  })

  it('only refreshes once for several concurrent 401s', async () => {
    setAccessToken('expired')

    apiMock.onGet('/a').replyOnce(401).onGet('/a').reply(200, { ok: 1 })
    apiMock.onGet('/b').replyOnce(401).onGet('/b').reply(200, { ok: 2 })
    apiMock.onGet('/c').replyOnce(401).onGet('/c').reply(200, { ok: 3 })

    let refreshCalls = 0
    bareMock.onPost('/auth/refresh').reply(() => {
      refreshCalls += 1
      return [200, { access_token: 'fresh', refresh_token: 'fresh-r' }]
    })

    await Promise.all([api.get('/a'), api.get('/b'), api.get('/c')])
    expect(refreshCalls).toBe(1)
  })

  it('clears the session and redirects when the refresh token itself is rejected', async () => {
    setAccessToken('expired')
    localStorage.setItem('user', JSON.stringify({ role: 'admin' }))

    apiMock.onGet('/protected').reply(401)
    bareMock.onPost('/auth/refresh').reply(401, { detail: 'refresh token expired' })

    await expect(api.get('/protected')).rejects.toBeTruthy()
    expect(getAccessToken()).toBeNull()
    expect(localStorage.getItem('user')).toBeNull()
    expect(window.location.href).toBe('/login')
  })

  it('does not attempt to refresh a 401 from the auth endpoints themselves', async () => {
    apiMock.onPost('/auth/login').reply(401, { detail: 'bad credentials' })
    let refreshCalls = 0
    bareMock.onPost('/auth/refresh').reply(() => { refreshCalls += 1; return [200, {}] })

    await expect(api.post('/auth/login', {})).rejects.toBeTruthy()
    expect(refreshCalls).toBe(0)
  })

  it('does not retry forever if the refreshed request 401s again', async () => {
    setAccessToken('expired')

    apiMock.onGet('/still-broken').reply(401)  // 401 every single time
    let refreshCalls = 0
    bareMock.onPost('/auth/refresh').reply(() => {
      refreshCalls += 1
      return [200, { access_token: 'fresh', refresh_token: 'fresh-r' }]
    })

    // Must settle (reject) rather than loop forever retrying-refreshing-retrying.
    await expect(api.get('/still-broken')).rejects.toBeTruthy()
    // A second 401 on the retried request must not trigger a second refresh
    // attempt -- that's the actual infinite-loop guard (`_retried`).
    expect(refreshCalls).toBe(1)
  })

  it('recovers after a refresh failure once the user logs back in', async () => {
    // Regression test: an earlier version only cleared the shared
    // refreshPromise via .finally() on the success branch, so a rejection
    // left it permanently stuck -- every later refresh attempt reused that
    // same stale rejected promise, even after a fresh login/refresh
    // supplied a valid credential.
    bareMock.onPost('/auth/refresh').replyOnce(401)
    apiMock.onGet('/protected').reply(401)
    await expect(api.get('/protected')).rejects.toBeTruthy()

    // "user logs back in" / cookie becomes valid again
    setAccessToken('expired-again')
    let calls = 0
    apiMock.onGet('/protected2').reply(() => {
      calls += 1
      return calls === 1 ? [401] : [200, { ok: true }]
    })
    bareMock.onPost('/auth/refresh').reply(200, {
      access_token: 'fresh', refresh_token: 'fresh-r',
    })

    const res = await api.get('/protected2')
    expect(res.data).toEqual({ ok: true })
  })

  it('leaves non-401 errors alone', async () => {
    apiMock.onGet('/broken').reply(500, { detail: 'server error' })
    await expect(api.get('/broken')).rejects.toMatchObject({
      response: { status: 500 },
    })
    expect(getAccessToken()).toBeNull() // untouched, was never set
  })
})
