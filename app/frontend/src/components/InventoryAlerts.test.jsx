import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import InventoryAlerts from './InventoryAlerts.jsx'

afterEach(cleanup)

const alerts = [
  { station_id: 'S01', display_name: 'Robert Purcell Community Center', status: 'empty', bikes: 0 },
  { station_id: 'S02', display_name: 'Appel Commons', status: 'full', bikes: 30 },
]
const handlers = () => ({ onOpen: vi.fn(), onDismiss: vi.fn(), onHover: vi.fn(), onFocus: vi.fn() })

describe('station inventory alert strip', () => {
  it('shows each station and critical state with independent open and dismiss controls', () => {
    const callbacks = handlers()
    render(<InventoryAlerts alerts={alerts} highlightedStation="S02" {...callbacks} />)
    const strip = screen.getByRole('region', { name: 'Station inventory alerts' })
    expect(strip.getAttribute('aria-live')).toBe('polite')
    const first = within(strip).getByRole('button', { name: 'S01 empty: Robert Purcell Community Center. Open live chart' })
    const second = within(strip).getByRole('button', { name: 'S02 full: Appel Commons. Open live chart' })
    expect(within(strip).getByText('S01 · Empty')).toBeTruthy()
    expect(within(strip).getByText('S02 · Full')).toBeTruthy()
    expect(first.closest('.inventory-alert').classList.contains('linked-highlight')).toBe(false)
    expect(second.closest('.inventory-alert').classList.contains('linked-highlight')).toBe(true)
    fireEvent.click(first)
    expect(callbacks.onOpen).toHaveBeenCalledWith('S01')
    expect(callbacks.onDismiss).not.toHaveBeenCalled()
    expect(within(strip).getAllByRole('button', { name: /^Dismiss/ })).toHaveLength(2)
  })

  it('dismisses without opening or bubbling and moves focus to the next station', () => {
    const callbacks = handlers()
    const onClick = vi.fn()
    const { rerender } = render(<div onClick={onClick}><InventoryAlerts alerts={alerts} {...callbacks} /></div>)
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss empty alert for S01' }))
    expect(callbacks.onDismiss).toHaveBeenCalledWith('S01')
    expect(callbacks.onOpen).not.toHaveBeenCalled()
    expect(onClick).not.toHaveBeenCalled()
    expect(callbacks.onHover).toHaveBeenCalledWith(null)
    expect(document.activeElement).toBe(screen.getByRole('button', { name: /^S02 full:/ }))
    rerender(<div onClick={onClick}><InventoryAlerts alerts={[alerts[1]]} {...callbacks} /></div>)
    expect(document.activeElement).toBe(screen.getByRole('button', { name: /^S02 full:/ }))
  })

  it('moves focus to the previous station when the last alert is dismissed', () => {
    const callbacks = handlers()
    render(<InventoryAlerts alerts={alerts} {...callbacks} />)
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss full alert for S02' }))
    expect(callbacks.onDismiss).toHaveBeenCalledWith('S02')
    expect(callbacks.onOpen).not.toHaveBeenCalled()
    expect(document.activeElement).toBe(screen.getByRole('button', { name: /^S01 empty:/ }))
  })

  it('links mouse and keyboard focus while retaining the station when focus moves within its alert', () => {
    const callbacks = handlers()
    render(<><InventoryAlerts alerts={alerts} {...callbacks} /><button>Outside</button></>)
    const open = screen.getByRole('button', { name: /^S01 empty:/ })
    const close = screen.getByRole('button', { name: 'Dismiss empty alert for S01' })
    const card = open.closest('.inventory-alert')
    fireEvent.mouseEnter(card)
    expect(callbacks.onHover).toHaveBeenLastCalledWith('S01')
    fireEvent.mouseLeave(card)
    expect(callbacks.onHover).toHaveBeenLastCalledWith(null)
    fireEvent.focus(open)
    expect(callbacks.onFocus).toHaveBeenLastCalledWith('S01')
    callbacks.onFocus.mockClear()
    fireEvent.blur(open, { relatedTarget: close })
    expect(callbacks.onFocus).not.toHaveBeenCalled()
    fireEvent.focus(close)
    expect(callbacks.onFocus).toHaveBeenLastCalledWith('S01')
    fireEvent.blur(close, { relatedTarget: screen.getByRole('button', { name: 'Outside' }) })
    expect(callbacks.onFocus).toHaveBeenLastCalledWith(null)
  })

  it.each([
    { loading: true, error: '', text: 'Checking current station readings…' },
    { loading: false, error: 'Network error', text: 'Current station alerts are unavailable.' },
    { loading: false, error: '', text: 'No active empty or full alerts.' },
  ])('explains the empty strip state: $text', ({ loading, error, text }) => {
    render(<InventoryAlerts alerts={[]} loading={loading} error={error} {...handlers()} />)
    expect(screen.getByText(text)).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
  })
})
