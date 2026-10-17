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
})
