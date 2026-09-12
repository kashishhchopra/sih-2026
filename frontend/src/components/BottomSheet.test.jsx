import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import BottomSheet from './BottomSheet.jsx'

describe('BottomSheet', () => {
  it('renders nothing when closed', () => {
    const { container } = render(<BottomSheet open={false} onClose={() => {}} title="Test" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders the title and children when open', () => {
    const { getByText } = render(
      <BottomSheet open={true} onClose={() => {}} title="Report">
        <div>panel content</div>
      </BottomSheet>
    )
    expect(getByText('Report')).toBeInTheDocument()
    expect(getByText('panel content')).toBeInTheDocument()
  })

  it('calls onClose when the backdrop is clicked', () => {
    const onClose = vi.fn()
    const { getByTestId } = render(<BottomSheet open={true} onClose={onClose} title="Report" />)
    fireEvent.click(getByTestId('sheet-backdrop'))
    expect(onClose).toHaveBeenCalled()
  })

  it('calls onClose when the close button is clicked', () => {
    const onClose = vi.fn()
    const { getByLabelText } = render(<BottomSheet open={true} onClose={onClose} title="Report" />)
    fireEvent.click(getByLabelText('Close'))
    expect(onClose).toHaveBeenCalled()
  })

  it('calls onClose on Escape', () => {
    const onClose = vi.fn()
    render(<BottomSheet open={true} onClose={onClose} title="Report" />)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })
})
