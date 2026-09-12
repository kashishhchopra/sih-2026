import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import '../../i18n' // initializes i18next so t() resolves real strings, not raw keys
import TouristTabBar from './TouristTabBar.jsx'

describe('TouristTabBar', () => {
  it('renders all four tabs', () => {
    const { getByText } = render(<TouristTabBar active="home" onChange={() => {}} />)
    expect(getByText('Home')).toBeInTheDocument()
    expect(getByText('Plan')).toBeInTheDocument()
    expect(getByText('Help')).toBeInTheDocument()
    expect(getByText('Me')).toBeInTheDocument()
  })

  it('marks the active tab via aria-current', () => {
    const { getByText } = render(<TouristTabBar active="plan" onChange={() => {}} />)
    expect(getByText('Plan').closest('button')).toHaveAttribute('aria-current', 'page')
    expect(getByText('Home').closest('button')).not.toHaveAttribute('aria-current')
  })

  it('calls onChange with the tab key when clicked', () => {
    const onChange = vi.fn()
    const { getByText } = render(<TouristTabBar active="home" onChange={onChange} />)
    fireEvent.click(getByText('Help'))
    expect(onChange).toHaveBeenCalledWith('help')
  })
})
