import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ColorFilterPills } from './FilterPills'

describe('ColorFilterPills', () => {
  it('renders and calls onChange when pill is clicked', () => {
    const onChange = vi.fn()
    render(<ColorFilterPills selected={[]} onChange={onChange} />)
    const buttons = screen.getAllByRole('button')
    expect(buttons.length).toBeGreaterThan(0)
    fireEvent.click(buttons[0])
    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith(expect.any(Array))
    expect(Array.isArray(onChange.mock.calls[0][0]) && onChange.mock.calls[0][0].length > 0).toBe(true)
  })

  it('toggles selection: clicking selected pill removes from selection', () => {
    const onChange = vi.fn()
    const { rerender } = render(<ColorFilterPills selected={['W']} onChange={onChange} />)
    const wButton = screen.getByTitle('White')
    fireEvent.click(wButton)
    expect(onChange).toHaveBeenCalledWith([])
    rerender(<ColorFilterPills selected={[]} onChange={onChange} />)
    fireEvent.click(wButton)
    expect(onChange).toHaveBeenLastCalledWith(['W'])
  })

  it('disabled pills do not call onChange', () => {
    const onChange = vi.fn()
    render(<ColorFilterPills selected={[]} onChange={onChange} disabled />)
    const buttons = screen.getAllByRole('button')
    fireEvent.click(buttons[0])
    expect(onChange).not.toHaveBeenCalled()
  })
})
