import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent, act } from '@testing-library/react'
import CctvStreamPlayer from './CctvStreamPlayer'

const cam = (over = {}) => ({
  id: 1, label: 'Plaza Cam', stream_url: 'https://cams.example.org/a/index.m3u8',
  stream_type: 'hls', connection: 'live', ...over,
})

describe('CctvStreamPlayer', () => {
  it('renders a video element for an HLS feed that is live', () => {
    const { container } = render(<CctvStreamPlayer camera={cam()} />)
    expect(container.querySelector('video')).toBeInTheDocument()
  })

  it('re-fetches a still-image camera so LIVE is not a frozen frame', async () => {
    vi.useFakeTimers()
    try {
      const { container } = render(<CctvStreamPlayer camera={cam({
        stream_type: 'jpeg', stream_url: 'https://cams.example.org/road/still.jpg',
      })} />)
      const first = container.querySelector('img').getAttribute('src')
      await act(async () => { vi.advanceTimersByTime(6000) })
      const second = container.querySelector('img').getAttribute('src')
      expect(second).not.toBe(first)          // a new frame was requested
      expect(second).toContain('https://cams.example.org/road/still.jpg')
    } finally {
      vi.useRealTimers()
    }
  })

  it('does not poll a still camera that is offline', async () => {
    vi.useFakeTimers()
    try {
      const { container } = render(<CctvStreamPlayer camera={cam({
        stream_type: 'jpeg', stream_url: 'https://cams.example.org/road/still.jpg',
        connection: 'offline',
      })} />)
      await act(async () => { vi.advanceTimersByTime(20000) })
      expect(container.querySelector('img')).not.toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('renders an <img> for an MJPEG feed, not a <video>', () => {
    const { container } = render(<CctvStreamPlayer camera={cam({
      stream_type: 'mjpeg', stream_url: 'http://cams.example.org/mjpg/video.mjpg',
    })} />)
    expect(container.querySelector('img')).toBeInTheDocument()
    expect(container.querySelector('video')).not.toBeInTheDocument()
  })

  it('plays an mp4 source directly on the video element', () => {
    const { container } = render(<CctvStreamPlayer camera={cam({
      stream_type: 'mp4', stream_url: 'https://cams.example.org/a.mp4',
    })} />)
    expect(container.querySelector('video')).toHaveAttribute(
      'src', 'https://cams.example.org/a.mp4')
  })

  it('says a camera is offline and offers a retry, showing no video', () => {
    const onRetry = vi.fn()
    const { getByText, container } = render(
      <CctvStreamPlayer camera={cam({ connection: 'offline' })} onRetry={onRetry} />)
    expect(getByText('CAMERA OFFLINE')).toBeInTheDocument()
    expect(getByText(/Unable to connect to camera/i)).toBeInTheDocument()
    expect(container.querySelector('video')).not.toBeInTheDocument()
    fireEvent.click(getByText(/Retry Connection/i))
    expect(onRetry).toHaveBeenCalled()
  })

  it('never renders a feed for a camera with no stream configured', () => {
    const { getByText, container } = render(<CctvStreamPlayer camera={cam({
      stream_url: null, stream_type: 'none', connection: 'no_stream',
    })} />)
    expect(getByText(/No Feed Configured/i)).toBeInTheDocument()
    expect(container.querySelector('video')).not.toBeInTheDocument()
    expect(container.querySelector('img')).not.toBeInTheDocument()
  })

  it('explains an RTSP feed cannot be played rather than showing a dead frame', () => {
    const { getByText, container } = render(<CctvStreamPlayer camera={cam({
      stream_type: 'rtsp', stream_url: 'rtsp://cams.example.org/live',
      connection: 'unplayable',
    })} />)
    expect(getByText(/Stream Not Viewable Here/i)).toBeInTheDocument()
    expect(container.querySelector('video')).not.toBeInTheDocument()
  })

  it('shows a connecting state before the first probe result', () => {
    const { getByText } = render(
      <CctvStreamPlayer camera={cam({ connection: 'unknown' })} />)
    expect(getByText(/Connecting to camera/i)).toBeInTheDocument()
  })

  it('reports a disabled camera as disabled, not offline', () => {
    const { getByText } = render(
      <CctvStreamPlayer camera={cam({ connection: 'disabled' })} />)
    expect(getByText(/Camera Disabled/i)).toBeInTheDocument()
  })

  it('marks a playback failure as offline and lets the operator retry', () => {
    const onRetry = vi.fn()
    const { container, getByText } = render(
      <CctvStreamPlayer camera={cam({ stream_type: 'mp4', stream_url: 'https://x/a.mp4' })}
        onRetry={onRetry} />)
    fireEvent.error(container.querySelector('video'))
    expect(getByText('CAMERA OFFLINE')).toBeInTheDocument()
    fireEvent.click(getByText(/Retry Connection/i))
    expect(onRetry).toHaveBeenCalled()
  })
})
