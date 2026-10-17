import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { Clock, IntervalSlider } from './Controls.jsx'

afterEach(cleanup)
const timestamps = ['2026-09-28T07:00:00-04:00', '2026-09-28T08:00:00-04:00', '2026-09-28T09:00:00-04:00']

describe('time controls', () => {
  it('labels both interval handles in Ithaca time and prevents an inverted range', () => {
    const onChange = vi.fn()
    render(<IntervalSlider interval={[1, 1]} max={2} timestamps={timestamps} timezone="America/New_York" onChange={onChange} />)
    const start = screen.getByRole('slider', { name: 'Analysis start' })
    const end = screen.getByRole('slider', { name: 'Analysis end' })
    expect(start.getAttribute('aria-valuetext')).toContain('08:00')
    fireEvent.change(start, { target: { value: '2' } })
    expect(onChange).toHaveBeenLastCalledWith([1, 1])
    fireEvent.change(end, { target: { value: '0' } })
    expect(onChange).toHaveBeenLastCalledWith([1, 1])
    fireEvent.change(screen.getByLabelText('Analysis start reading'), { target: { value: '0' } })
    expect(onChange).toHaveBeenLastCalledWith([0, 1])
  })
  it('disables Play in Analysis while keeping the shared clock editable', () => {
    const dispatch = vi.fn()
    render(<Clock state={{ config: { timestamps, timezone: 'America/New_York' }, cursor: 1, view: 'Analysis', playing: false }} dispatch={dispatch} />)
    expect(screen.getByRole('button', { name: /Play/ }).disabled).toBe(true)
    fireEvent.change(screen.getByRole('slider', { name: 'Simulation time' }), { target: { value: '2' } })
    expect(dispatch).toHaveBeenCalledWith({ type: 'setCursor', cursor: 2 })
    fireEvent.click(screen.getByRole('button', { name: '← Step' }))
    expect(dispatch).toHaveBeenCalledWith({ type: 'step', direction: -1 })
  })
})
