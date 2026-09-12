import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, fireEvent, waitFor, within } from '@testing-library/react'
import MockAdapter from 'axios-mock-adapter'
import api from '../api'
import CctvNetworkPanel from './CctvNetworkPanel'

const mock = new MockAdapter(api)

// Every camera in these tests comes from a mocked API response -- which is
// the point: the component has no camera list of its own to fall back on.
const camera = (over = {}) => ({
  id: 1, label: 'Railway Approach', zone_id: 3, lat: 26.1445, lng: 91.7362,
  status: 'active', stream_url: 'https://cams.example.org/a/index.m3u8',
  stream_type: 'hls', feed_source: 'City Traffic Authority', source_url: null,
  attribution: null, assigned_station_id: 7, connection: 'live',
  last_checked_at: new Date().toISOString(), ...over,
})

const network = (cameras, summary = {}) => ({
  cameras,
  summary: {
    total: cameras.length,
    live: cameras.filter((c) => c.connection === 'live').length,
    offline: cameras.filter((c) => c.connection === 'offline').length,
    no_stream: cameras.filter((c) => c.connection === 'no_stream').length,
    provider: null, provider_configured: false, refresh_interval_seconds: 0,
    ...summary,
  },
})

const stations = [{ id: 7, name: 'Central Station' }, { id: 8, name: 'Market Station' }]

beforeEach(() => { mock.reset() })

describe('CctvNetworkPanel', () => {
  it('shows a loading state while the network is being retrieved', () => {
    mock.onGet('/cctv').reply(() => new Promise(() => {})) // never resolves
    const { getByText } = render(<CctvNetworkPanel stations={stations} />)
    expect(getByText(/Loading CCTV Network/i)).toBeInTheDocument()
  })

  it('renders each camera returned by the API', async () => {
    mock.onGet('/cctv').reply(200, network([
      camera(), camera({ id: 2, label: 'Market Square', connection: 'offline' }),
    ]))
    const { findByText, getByText } = render(<CctvNetworkPanel stations={stations} />)
    expect(await findByText('Railway Approach')).toBeInTheDocument()
    expect(getByText('Market Square')).toBeInTheDocument()
  })

  it('adapts to any number of cameras, including many', async () => {
    const many = Array.from({ length: 20 }, (_, i) =>
      camera({ id: i + 1, label: `Camera ${i + 1}` }))
    mock.onGet('/cctv').reply(200, network(many))
    const { findByText, getByText } = render(<CctvNetworkPanel stations={stations} />)
    expect(await findByText('Camera 1')).toBeInTheDocument()
    expect(getByText('Camera 20')).toBeInTheDocument()
  })

  it('tells the operator when there are no feeds instead of inventing one', async () => {
    mock.onGet('/cctv').reply(200, network([]))
    const { findByText } = render(<CctvNetworkPanel stations={stations} />)
    expect(await findByText(/No live CCTV sources currently available/i)).toBeInTheDocument()
  })

  it('surfaces an API failure without taking the dashboard down', async () => {
    mock.onGet('/cctv').reply(500)
    const { findByText } = render(<CctvNetworkPanel stations={stations} />)
    expect(await findByText(/CCTV Network Unavailable/i)).toBeInTheDocument()
    expect(await findByText(/Unable to retrieve camera feeds/i)).toBeInTheDocument()
  })

  it('only labels a camera LIVE when the API says the connection is live', async () => {
    mock.onGet('/cctv').reply(200, network([
      camera({ id: 1, label: 'Streaming', connection: 'live' }),
      // status "active" in the DB but no feed -- must NOT read LIVE.
      camera({ id: 2, label: 'Directory Only', status: 'active',
        stream_url: null, stream_type: 'none', connection: 'no_stream' }),
    ]))
    const { findByText, getByText, queryAllByText } = render(<CctvNetworkPanel stations={stations} />)
    await findByText('Streaming')
    expect(queryAllByText('LIVE')).toHaveLength(1)
    expect(getByText('NO FEED')).toBeInTheDocument()
    // "No feed" is also one of the filter dropdown's own <option> labels;
    // the compact overlay's copy is the one that isn't inside a <select>.
    const noFeedLabel = getByText('No feed', { selector: 'div' })
    expect(noFeedLabel).toBeInTheDocument()
  })

  it('offers a retry on an offline camera and reflects a recovered feed', async () => {
    // The grid tile shows a short "Offline" label only (see the compact-
    // overlay regression test below); Retry lives in the expanded view,
    // reached by tapping the tile.
    mock.onGet('/cctv').reply(200, network([camera({ connection: 'offline' })]))
    mock.onGet('/cctv/1/status').reply(200, {
      id: 1, connection: 'live', last_checked_at: new Date().toISOString(),
    })
    const { findByText, getByText, queryAllByText } = render(<CctvNetworkPanel stations={stations} />)
    await findByText('Offline', { selector: 'div' })  // the tile's own label, not the filter <option>
    fireEvent.click(getByText('Railway Approach'))
    expect(await findByText(/CAMERA OFFLINE/i)).toBeInTheDocument()
    fireEvent.click(getByText(/Retry Connection/i))
    await waitFor(() => expect(queryAllByText('LIVE').length).toBeGreaterThan(0))
  })

  it("keeps a compact grid tile's offline/unavailable label short enough not to collide with its badge (regression)", async () => {
    // What broke: the tile is ~96px tall, but the full overlay (title +
    // detail line + Retry button) needed far more room, so it overflowed
    // upward into the badge pinned at the tile's top-left corner --
    // "UNAVAILABLE" (badge) rendering right on top of "CAMERA UNAVAILABLE"
    // (overlay title) read as garbled overlapping text on screen.
    mock.onGet('/cctv').reply(200, network([
      camera({ id: 1, label: 'A', connection: 'unavailable' }),
      camera({ id: 2, label: 'B', connection: 'offline' }),
    ]))
    const { findByText, queryByText } = render(<CctvNetworkPanel stations={stations} />)
    await findByText('A')
    // The long titles/detail text/Retry button must NOT appear in the grid.
    expect(queryByText(/CAMERA UNAVAILABLE/i)).not.toBeInTheDocument()
    expect(queryByText(/CAMERA OFFLINE/i)).not.toBeInTheDocument()
    expect(queryByText(/publishing an 'unavailable' notice/i)).not.toBeInTheDocument()
    expect(queryByText(/Unable to connect to camera/i)).not.toBeInTheDocument()
    expect(queryByText(/Retry Connection/i)).not.toBeInTheDocument()
    // The short compact labels are what's actually shown (scoped past the
    // filter dropdown's own "Offline"/"No feed" <option> text).
    expect(queryByText('Unavailable', { selector: 'div' })).toBeInTheDocument()
    expect(queryByText('Offline', { selector: 'div' })).toBeInTheDocument()
  })

  it('shows the assigned police station from the API, not a local mapping', async () => {
    mock.onGet('/cctv').reply(200, network([camera({ assigned_station_id: 8 })]))
    const { findByText } = render(<CctvNetworkPanel stations={stations} />)
    expect(await findByText(/Market Station/)).toBeInTheDocument()
  })

  it('sends filters to the backend rather than filtering in the browser', async () => {
    mock.onGet('/cctv').reply(200, network([camera()]))
    const { findByText, getByLabelText } = render(<CctvNetworkPanel stations={stations} />)
    await findByText('Railway Approach')
    fireEvent.change(getByLabelText('Filter by police station'), { target: { value: '8' } })
    await waitFor(() => {
      const last = mock.history.get[mock.history.get.length - 1]
      expect(last.params.station_id).toBe(8)
    })
    fireEvent.change(getByLabelText('Filter by status'), { target: { value: 'live' } })
    await waitFor(() => {
      const last = mock.history.get[mock.history.get.length - 1]
      expect(last.params.connection).toBe('live')
    })
  })

  it('passes a search term to the backend', async () => {
    mock.onGet('/cctv').reply(200, network([camera()]))
    const { findByText, getByLabelText } = render(<CctvNetworkPanel stations={stations} />)
    await findByText('Railway Approach')
    fireEvent.change(getByLabelText('Search cameras'), { target: { value: 'railway' } })
    await waitFor(() => {
      const last = mock.history.get[mock.history.get.length - 1]
      expect(last.params.q).toBe('railway')
    })
  })

  it('hands the loaded cameras up so the map can place markers from them', async () => {
    const onCamerasLoaded = vi.fn()
    mock.onGet('/cctv').reply(200, network([camera()]))
    render(<CctvNetworkPanel stations={stations} onCamerasLoaded={onCamerasLoaded} />)
    await waitFor(() => expect(onCamerasLoaded).toHaveBeenCalled())
    const passed = onCamerasLoaded.mock.calls.at(-1)[0]
    expect(passed[0].lat).toBe(26.1445)
    expect(passed[0].lng).toBe(91.7362)
  })

  it('selecting a camera asks the map to focus it', async () => {
    const onFocusCamera = vi.fn()
    mock.onGet('/cctv').reply(200, network([camera()]))
    const { findByText } = render(
      <CctvNetworkPanel stations={stations} onFocusCamera={onFocusCamera} />)
    fireEvent.click(await findByText('Railway Approach'))
    expect(onFocusCamera).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }))
  })

  it('opens the feed a map marker asked for', async () => {
    const onOpenHandled = vi.fn()
    mock.onGet('/cctv').reply(200, network([camera()]))
    const { findByRole } = render(
      <CctvNetworkPanel stations={stations} openCameraId={1} onOpenHandled={onOpenHandled} />)
    const dialog = await findByRole('dialog')
    expect(within(dialog).getByText('Railway Approach')).toBeInTheDocument()
    expect(onOpenHandled).toHaveBeenCalled()
  })

  it('reads naive UTC timestamps as UTC, not local time (regression)', async () => {
    // The API serialises "2026-09-09T12:46:25" with no zone suffix. Read as
    // local time in +05:30 that made a probe from seconds ago render as
    // "6h ago" on every card.
    const naiveUtcNow = new Date().toISOString().replace('Z', '').split('.')[0]
    mock.onGet('/cctv').reply(200, network([camera({ last_checked_at: naiveUtcNow })]))
    const { findByText, queryByText } = render(<CctvNetworkPanel stations={stations} />)
    await findByText('Railway Approach')
    expect(queryByText(/\dh ago/)).not.toBeInTheDocument()
  })

  it('shows a camera serving an unavailable notice as such, not as live', async () => {
    mock.onGet('/cctv').reply(200, network([
      camera({ label: 'Down For Construction', connection: 'unavailable' }),
    ], { live: 0, unavailable: 1 }))
    const { findByText, getByText, queryByText } = render(<CctvNetworkPanel stations={stations} />)
    expect(await findByText('UNAVAILABLE')).toBeInTheDocument()
    expect(queryByText('LIVE')).not.toBeInTheDocument()
    // Full explanation lives in the expanded view, not the grid tile.
    fireEvent.click(getByText('Down For Construction'))
    expect(await findByText(/CAMERA UNAVAILABLE/i)).toBeInTheDocument()
  })

  it('removes a camera after a second confirming tap', async () => {
    mock.onGet('/cctv').reply(200, network([camera()]))
    mock.onDelete('/cctv/1').reply(204)
    const { findByText, getByText, queryByText } = render(<CctvNetworkPanel stations={stations} />)
    fireEvent.click(await findByText('Railway Approach'))
    const removeBtn = await findByText('Remove camera')
    fireEvent.click(removeBtn)
    expect(await findByText(/Tap again to confirm/i)).toBeInTheDocument()
    // one tap alone must not have deleted anything yet
    expect(mock.history.delete.length).toBe(0)
    fireEvent.click(getByText(/Tap again to confirm/i))
    await waitFor(() => expect(mock.history.delete.length).toBe(1))
    // the modal closes and the (now only) camera disappears from the grid
    await waitFor(() => expect(queryByText('Railway Approach')).not.toBeInTheDocument())
  })

  it('surfaces a failed camera removal without crashing the console', async () => {
    mock.onGet('/cctv').reply(200, network([camera()]))
    mock.onDelete('/cctv/1').reply(403)
    const { findByText, getByText, getAllByText } = render(<CctvNetworkPanel stations={stations} />)
    fireEvent.click(await findByText('Railway Approach'))
    fireEvent.click(await findByText('Remove camera'))
    fireEvent.click(getByText(/Tap again to confirm/i))
    expect(await findByText(/Unable to remove this camera/i)).toBeInTheDocument()
    // The camera is still there -- a failed delete must not silently drop
    // it, AND it must not hide the rest of the grid behind a false
    // "CCTV Network Unavailable" screen (a real bug this guards against:
    // reusing the network-fetch error state for a delete failure did
    // exactly that). Two matches now -- the grid tile plus the still-open
    // modal -- is the correct outcome.
    expect(getAllByText('Railway Approach').length).toBe(2)
  })

  it('credits the feed source in the expanded view', async () => {
    mock.onGet('/cctv').reply(200, network([
      camera({ attribution: 'Open Data Licence', source_url: 'https://example.org/about' }),
    ]))
    const { findByText, findByRole } = render(<CctvNetworkPanel stations={stations} />)
    fireEvent.click(await findByText('Railway Approach'))
    const dialog = await findByRole('dialog')
    expect(within(dialog).getByText(/City Traffic Authority/)).toBeInTheDocument()
    expect(within(dialog).getByText(/Open Data Licence/)).toBeInTheDocument()
  })
})
