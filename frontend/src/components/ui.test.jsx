import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { bandColor, bandLabel, ScoreGauge, SeverityBadge, StatusBadge, Stat, Card } from './ui.jsx'

// The band thresholds are the safety model's user-facing contract and must match
// band_for() in backend/app/services/safety.py exactly.
describe('safety band thresholds', () => {
  it.each([
    [100, 'Safe'], [75, 'Safe'],
    [74.9, 'Moderate'], [50, 'Moderate'],
    [49.9, 'Risky'], [25, 'Risky'],
    [24.9, 'Danger'], [0, 'Danger'],
  ])('score %s is labelled %s', (score, label) => {
    expect(bandLabel(score)).toBe(label)
  })

  it('assigns a distinct colour per band', () => {
    const colors = [100, 60, 30, 10].map(bandColor)
    expect(new Set(colors).size).toBe(4)
  })

  it('agrees between colour and label at every boundary', () => {
    expect(bandColor(75)).not.toBe(bandColor(74.9))
    expect(bandColor(50)).not.toBe(bandColor(49.9))
    expect(bandColor(25)).not.toBe(bandColor(24.9))
  })
})

describe('ScoreGauge', () => {
  it('renders the rounded score and its band', () => {
    render(<ScoreGauge score={82.4} />)
    expect(screen.getByText('82')).toBeInTheDocument()
    expect(screen.getByText('Safe')).toBeInTheDocument()
  })

  it('clamps out-of-range scores instead of overflowing the arc', () => {
    const { container } = render(<ScoreGauge score={150} />)
    const arc = container.querySelectorAll('circle')[1]
    expect(Number(arc.getAttribute('stroke-dashoffset'))).toBeCloseTo(0, 5)
  })

  it('handles a zero score', () => {
    render(<ScoreGauge score={0} />)
    expect(screen.getByText('Danger')).toBeInTheDocument()
  })
})

describe('badges', () => {
  it('renders each severity', () => {
    for (const s of ['low', 'medium', 'high', 'critical']) {
      const { unmount } = render(<SeverityBadge severity={s} />)
      expect(screen.getByText(s)).toBeInTheDocument()
      unmount()
    }
  })

  it('falls back gracefully for an unknown severity', () => {
    render(<SeverityBadge severity="unheard-of" />)
    expect(screen.getByText('unheard-of')).toBeInTheDocument()
  })

  it('renders incident and tourist statuses', () => {
    for (const s of ['active', 'sos', 'missing', 'detected', 'resolved']) {
      const { unmount } = render(<StatusBadge status={s} />)
      expect(screen.getByText(s)).toBeInTheDocument()
      unmount()
    }
  })
})

describe('layout helpers', () => {
  it('Stat shows its label and value', () => {
    render(<Stat label="Open Incidents" value={7} />)
    expect(screen.getByText('Open Incidents')).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()
  })

  it('Card renders its title and children', () => {
    render(<Card title="Itinerary"><p>Kamakhya Temple</p></Card>)
    expect(screen.getByText('Itinerary')).toBeInTheDocument()
    expect(screen.getByText('Kamakhya Temple')).toBeInTheDocument()
  })

  it('Card omits the header when untitled', () => {
    const { container } = render(<Card><p>body</p></Card>)
    expect(container.querySelector('h3')).toBeNull()
  })
})
