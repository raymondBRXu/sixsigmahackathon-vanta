import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { Clock, DateRangeSlider } from './Controls.jsx'

afterEach(cleanup)
const timestamps = ['2026-09-28T07:00:00-04:00', '2026-09-28T08:00:00-04:00', '2026-09-28T09:00:00-04:00']
const dates = ['2026-09-28', '2026-09-30', '2026-10-01']

describe('time controls', () => {
  it('disables both range handles and both date selectors while diagnosis is active', () => {
    const { rerender } = render(<DateRangeSlider dateRange={[0, 2]} max={2} dates={dates} disabled onChange={() => {}} />)
    for (const control of [...screen.getAllByRole('slider'), ...screen.getAllByRole('combobox')]) {
      expect(control.disabled).toBe(true)
    }
    rerender(<DateRangeSlider dateRange={[0, 2]} max={2} dates={dates} onChange={() => {}} />)
    for (const control of [...screen.getAllByRole('slider'), ...screen.getAllByRole('combobox')]) {
      expect(control.disabled).toBe(false)
    }
  })
  it('labels both handles with service dates and prevents an inverted range', () => {
    const onChange = vi.fn()
    render(<DateRangeSlider dateRange={[1, 1]} max={2} dates={dates} onChange={onChange} />)
    const start = screen.getByRole('slider', { name: 'Analysis start date' })
    const end = screen.getByRole('slider', { name: 'Analysis end date' })
    expect(start.getAttribute('aria-valuetext')).toBe('Sep 30, 2026')
    fireEvent.change(start, { target: { value: '2' } })
    expect(onChange).toHaveBeenLastCalledWith([1, 1])
    fireEvent.change(end, { target: { value: '0' } })
    expect(onChange).toHaveBeenLastCalledWith([1, 1])
    fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '0' } })
    expect(onChange).toHaveBeenLastCalledWith([0, 1])
  })
  it('keeps date-only labels stable and shows just the configured date range', () => {
    render(<DateRangeSlider dateRange={[0, 0]} max={0} dates={dates} onChange={() => {}} />)
    const start = screen.getByRole('slider', { name: 'Analysis start date' })
    expect(start.getAttribute('aria-valuetext')).toBe('Sep 28, 2026')
    expect(start.disabled).toBe(true)
    expect(screen.getByLabelText('End date').options).toHaveLength(1)
    expect(screen.queryByText('Sep 30, 2026')).toBeNull()
  })
  it('disables Play while History is open', () => {
    const dispatch = vi.fn()
    render(<Clock state={{ config: { timestamps, timezone: 'America/New_York' }, cursor: 1, historyStation: 'S01', playing: false }} dispatch={dispatch} />)
    expect(screen.getByRole('button', { name: /Play/ }).disabled).toBe(true)
    fireEvent.change(screen.getByRole('slider', { name: 'Simulation time' }), { target: { value: '2' } })
    expect(dispatch).toHaveBeenCalledWith({ type: 'setCursor', cursor: 2 })
    fireEvent.click(screen.getByRole('button', { name: '← Step' }))
    expect(dispatch).toHaveBeenCalledWith({ type: 'step', direction: -1 })
  })
})
