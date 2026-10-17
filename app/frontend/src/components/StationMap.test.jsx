import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import StationMap from './StationMap.jsx'

const { instances } = vi.hoisted(() => ({ instances: [] }))
vi.mock('maplibre-gl', () => ({
  setWorkerUrl: vi.fn(),
  Map: class {
    constructor(options) { this.container = options.container; instances.push(this) }
    addControl() {}
    on() {}
    off() {}
    once() {}
    isStyleLoaded() { return true }
    setLayoutProperty() {}
    setStyle = vi.fn()
    resize() {}
    remove() {}
    getCenter() { return { toArray: () => [-76.49, 42.45] } }
    getZoom() { return 13 }
  },
  Marker: class {
    constructor({ element }) { this.element = element }
    setLngLat() { return this }
    addTo(map) { map.container.append(this.element); return this }
    remove() { this.element.remove() }
  },
  Popup: class {
    setLngLat() { return this }
    setDOMContent(element) { this.element = element; return this }
    addTo(map) { map.container.append(this.element); return this }
    remove() { this.element?.remove() }
  },
  NavigationControl: class {},
}))

vi.stubGlobal('ResizeObserver', class { observe() {}; disconnect() {} })
afterEach(() => { cleanup(); instances.length = 0 })

const station = {
  station_id: 'S01', display_name: 'Robert Purcell Community Center', longitude: -76.477486,
  latitude: 42.455906, bikes: 0, free_docks: 30, capacity: 30, status: 'empty',
  suggested_change: 15, action: 'Add bikes', latest_bikes: 0, age_minutes: 0,
  latest_timestamp: '2026-09-28T09:00:00-04:00',
}

describe('station map interactions', () => {
  it('selects only on marker double-click or keyboard, never a single click or background double-click', () => {
    const onSelect = vi.fn()
    render(<StationMap stations={[station]} selected="S20" tiles timezone="America/New_York" onSelect={onSelect} camera={{ current: null }} />)
    const marker = screen.getByRole('button', { name: /S01 · Robert Purcell/ })
    fireEvent.click(marker)
    expect(onSelect).not.toHaveBeenCalled()
    fireEvent.doubleClick(screen.getByLabelText('Map of 20 simulated Ithaca bikeshare stations'))
    expect(onSelect).not.toHaveBeenCalled()
    fireEvent.doubleClick(marker)
    expect(onSelect).toHaveBeenCalledExactlyOnceWith('S01')
    fireEvent.keyDown(marker, { key: 'Enter' })
    expect(onSelect).toHaveBeenCalledTimes(2)
  })
  it('shows measured zero distinctly from missing and keeps the map instance when readings change', () => {
    const props = { selected: 'S01', tiles: true, timezone: 'America/New_York', onSelect: vi.fn(), camera: { current: null } }
    const { rerender } = render(<StationMap {...props} stations={[station]} />)
    const marker = screen.getByRole('button', { name: /S01 · Robert Purcell/ })
    fireEvent.mouseEnter(marker)
    expect(screen.getByText('Current bikes: 0 / 30')).toBeTruthy()
    fireEvent.mouseLeave(marker)
    rerender(<StationMap {...props} stations={[{ ...station, bikes: null, free_docks: null, status: 'stale', age_minutes: 60, suggested_change: null }]} />)
    expect(instances).toHaveLength(1)
    expect(screen.getByRole('button', { name: /S01 · Robert Purcell/ })).toBe(marker)
    fireEvent.mouseEnter(marker)
    expect(screen.getByText('Current bikes: — / 30')).toBeTruthy()
    expect(screen.getByText('Reading age: 60 min')).toBeTruthy()
    expect(marker.classList.contains('selected')).toBe(true)
  })
  it('preserves markers and the camera across loading and basemap switches', () => {
    const props = { selected: 'S01', timezone: 'America/New_York', onSelect: vi.fn(), camera: { current: null } }
    const { rerender, unmount } = render(<StationMap {...props} tiles stations={[station]} />)
    const marker = screen.getByRole('button', { name: /S01 · Robert Purcell/ })
    rerender(<StationMap {...props} tiles stations={[]} />)
    expect(screen.getByRole('button', { name: /S01 · Robert Purcell/ })).toBe(marker)
    rerender(<StationMap {...props} tiles={false} stations={[station]} />)
    expect(instances[0].setStyle).toHaveBeenLastCalledWith(expect.objectContaining({ sources: {} }))
    rerender(<StationMap {...props} tiles stations={[station]} />)
    expect(instances[0].setStyle).toHaveBeenLastCalledWith('https://tiles.openfreemap.org/styles/positron')
    expect(instances).toHaveLength(1)
    unmount()
    expect(props.camera.current).toEqual({ center: [-76.49, 42.45], zoom: 13 })
  })
  it('links marker hover and keyboard focus through current callbacks while retaining popups', () => {
    const onHoverStation = vi.fn()
    const onFocusStation = vi.fn()
    const props = { stations: [station], selected: 'S20', tiles: true, timezone: 'America/New_York',
      onSelect: vi.fn(), camera: { current: null }, onHoverStation, onFocusStation }
    const { rerender } = render(<StationMap {...props} />)
    const marker = screen.getByRole('button', { name: /S01 · Robert Purcell/ })
    fireEvent.mouseEnter(marker)
    expect(onHoverStation).toHaveBeenLastCalledWith('S01')
    expect(screen.getByText('Current bikes: 0 / 30')).toBeTruthy()
    fireEvent.mouseLeave(marker)
    expect(onHoverStation).toHaveBeenLastCalledWith(null)
    expect(screen.queryByText('Current bikes: 0 / 30')).toBeNull()

    const nextHover = vi.fn()
    const nextFocus = vi.fn()
    rerender(<StationMap {...props} onHoverStation={nextHover} onFocusStation={nextFocus} />)
    fireEvent.focus(marker)
    expect(nextFocus).toHaveBeenCalledExactlyOnceWith('S01')
    expect(onFocusStation).not.toHaveBeenCalled()
    fireEvent.mouseEnter(marker)
    expect(nextHover).toHaveBeenLastCalledWith('S01')
    expect(onHoverStation).toHaveBeenCalledTimes(2)
    fireEvent.mouseLeave(marker)
    expect(nextHover).toHaveBeenLastCalledWith(null)
    expect(screen.getByText('Current bikes: 0 / 30')).toBeTruthy()
    fireEvent.blur(marker)
    expect(nextFocus).toHaveBeenLastCalledWith(null)
    expect(screen.queryByText('Current bikes: 0 / 30')).toBeNull()
    expect(props.onSelect).not.toHaveBeenCalled()
    expect(instances).toHaveLength(1)
  })
  it('moves one linked halo without changing selection, marker position or the map instance', () => {
    const second = { ...station, station_id: 'S02', display_name: 'Second station', longitude: -76.48 }
    const props = { stations: [station, second], selected: 'S01', tiles: true, timezone: 'America/New_York',
      onSelect: vi.fn(), camera: { current: null } }
    const { rerender } = render(<StationMap {...props} highlightedStation="S01" />)
    const firstMarker = screen.getByRole('button', { name: /S01 · Robert Purcell/ })
    const secondMarker = screen.getByRole('button', { name: /S02 · Second station/ })
    firstMarker.style.transform = 'translate(120px, 80px)'
    secondMarker.style.transform = 'translate(220px, 160px)'
    expect(firstMarker.classList.contains('linked-highlight')).toBe(true)
    expect(secondMarker.classList.contains('linked-highlight')).toBe(false)

    rerender(<StationMap {...props} highlightedStation="S02" />)
    expect(firstMarker.classList.contains('linked-highlight')).toBe(false)
    expect(secondMarker.classList.contains('linked-highlight')).toBe(true)
    expect(firstMarker.classList.contains('selected')).toBe(true)
    expect(firstMarker.getAttribute('aria-pressed')).toBe('true')
    expect(secondMarker.classList.contains('selected')).toBe(false)
    expect(secondMarker.getAttribute('aria-pressed')).toBe('false')
    expect(firstMarker.style.transform).toBe('translate(120px, 80px)')
    expect(secondMarker.style.transform).toBe('translate(220px, 160px)')

    rerender(<StationMap {...props} highlightedStation={null} />)
    expect(screen.getByLabelText('Map of 20 simulated Ithaca bikeshare stations').querySelectorAll('.linked-highlight')).toHaveLength(0)
    expect(screen.getByRole('button', { name: /S01 · Robert Purcell/ })).toBe(firstMarker)
    expect(screen.getByRole('button', { name: /S02 · Second station/ })).toBe(secondMarker)
    expect(firstMarker.classList.contains('selected')).toBe(true)
    expect(instances).toHaveLength(1)
    expect(props.camera.current).toBeNull()
  })
  it('clears stale halos and interactions during loading while retaining markers and selection', () => {
    const props = { selected: 'S01', tiles: true, timezone: 'America/New_York', onSelect: vi.fn(),
      onHoverStation: vi.fn(), onFocusStation: vi.fn(), camera: { current: null }, highlightedStation: 'S01' }
    const { rerender } = render(<StationMap {...props} stations={[station]} />)
    const marker = screen.getByRole('button', { name: /S01 · Robert Purcell/ })
    fireEvent.mouseEnter(marker)
    fireEvent.focus(marker)
    expect(marker.classList.contains('linked-highlight')).toBe(true)
    rerender(<StationMap {...props} stations={[]} />)
    expect(marker.classList.contains('linked-highlight')).toBe(false)
    expect(marker.classList.contains('selected')).toBe(true)
    expect(props.onHoverStation).toHaveBeenLastCalledWith(null)
    expect(props.onFocusStation).toHaveBeenLastCalledWith(null)
    expect(screen.queryByText('Current bikes: 0 / 30')).toBeNull()
    fireEvent.mouseEnter(marker)
    fireEvent.focus(marker)
    expect(props.onHoverStation).toHaveBeenCalledTimes(2)
    expect(props.onFocusStation).toHaveBeenCalledTimes(2)
    expect(screen.queryByText('Current bikes: 0 / 30')).toBeNull()
    expect(screen.getByRole('button', { name: /S01 · Robert Purcell/ })).toBe(marker)
    rerender(<StationMap {...props} stations={[station]} highlightedStation={null} />)
    expect(marker.classList.contains('linked-highlight')).toBe(false)
    expect(instances).toHaveLength(1)
  })
  it('releases a removed or unmounted marker without leaving its linked halo or interaction', () => {
    const second = { ...station, station_id: 'S02', display_name: 'Second station' }
    const props = { selected: 'S01', tiles: true, timezone: 'America/New_York', onSelect: vi.fn(),
      onHoverStation: vi.fn(), onFocusStation: vi.fn(), camera: { current: null } }
    const { rerender, unmount } = render(<StationMap {...props} stations={[station, second]} highlightedStation="S01" />)
    const firstMarker = screen.getByRole('button', { name: /S01 · Robert Purcell/ })
    fireEvent.mouseEnter(firstMarker)
    fireEvent.focus(firstMarker)
    rerender(<StationMap {...props} stations={[second]} highlightedStation="S02" />)
    expect(firstMarker.isConnected).toBe(false)
    expect(firstMarker.classList.contains('linked-highlight')).toBe(false)
    expect(props.onHoverStation).toHaveBeenLastCalledWith(null)
    expect(props.onFocusStation).toHaveBeenLastCalledWith(null)
    const secondMarker = screen.getByRole('button', { name: /S02 · Second station/ })
    fireEvent.mouseEnter(secondMarker)
    expect(secondMarker.classList.contains('linked-highlight')).toBe(true)
    unmount()
    expect(secondMarker.classList.contains('linked-highlight')).toBe(false)
    expect(props.onHoverStation).toHaveBeenLastCalledWith(null)
    expect(props.camera.current).toEqual({ center: [-76.49, 42.45], zoom: 13 })
  })
})
