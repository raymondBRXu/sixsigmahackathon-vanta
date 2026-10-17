import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App.jsx'

vi.mock('./components/StationMap.jsx', () => ({ default: () => <div aria-label="Station map" /> }))

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers() })

const timestamps = [7, 8, 9, 10, 11].map((hour) => `2026-09-28T${String(hour).padStart(2, '0')}:00:00-04:00`)
const stations = [
  { station_id: 'S01', display_name: 'Robert Purcell Community Center', capacity: 30 },
  { station_id: 'S02', display_name: 'Appel Commons', capacity: 30 },
]
const scenarios = [{ id: 'normal', label: 'Normal operations' }, { id: 'edge_cases', label: 'Edge cases' }]

function mockApi({ missing = false, uploadError = false } = {}) {
  const config = (source) => ({ source: { id: source, label: `${source}.csv`, observations: 10 }, timestamps, timezone: 'America/New_York', stations, scenarios, default_cursor: 2 })
  const rows = stations.map((station, index) => ({
    ...station, bikes: index === 0 ? missing ? null : 18 : 0, free_docks: index === 0 ? missing ? null : 12 : 30,
    status: index === 0 ? missing ? 'stale' : 'normal' : 'empty', net_change: null,
    latest_bikes: 18, latest_timestamp: timestamps[1], age_minutes: 60,
    suggested_change: index === 0 ? missing ? null : 0 : 15,
  }))
  const fetch = vi.fn(async (url) => {
    const request = new URL(url)
    if (request.pathname.endsWith('/uploads') && uploadError) return { ok: false, status: 422, json: async () => ({ detail: 'Duplicate station/timestamp rows are not allowed.' }) }
    const payload = request.pathname.endsWith('/config') ? config(request.searchParams.get('source'))
      : request.pathname.endsWith('/snapshot') ? {
        stations: rows, queue: rows.filter((row) => row.status !== 'normal'),
        metrics: { availability: missing ? 0 : 0.5, available_count: missing ? 0 : 1, empty_count: 1, full_count: 0, n: missing ? 1 : 2, planned: 2, empty_rate: missing ? 1 : 0.5, full_rate: 0, coverage: missing ? 0.5 : 1 },
      } : {
        summary: { n: 3, planned: 3, pairs: 2, cl: 18.67, limits: { lcl: 13.35, ucl: 23.99, mr_mean: 2, sigma: 1.773 }, reason: '' },
      }
    return { ok: true, json: async () => payload }
  })
  vi.stubGlobal('fetch', fetch)
  return fetch
}

describe('dashboard end-to-end component wiring', () => {
  it('renders named queue entries and keeps missing counts separate from zero', async () => {
    mockApi({ missing: true })
    render(<App />)
    await screen.findByText('— / 30')
    expect(screen.getByText(/Last reading: 18 bikes/)).toBeTruthy()
    const queue = screen.getByRole('table')
    expect(within(queue).getByText('Appel Commons')).toBeTruthy()
    expect(within(queue).getByText('Reinspect')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Station'), { target: { value: 'S02' } })
    expect(await screen.findByText('0 / 30')).toBeTruthy()
    expect(screen.getByRole('link', { name: /Download current snapshot/ }).href).toContain('/api/snapshot.csv?source=normal&cursor=2')
  })
  it('uses the Python analysis endpoint and chart images for all selected hourly readings', async () => {
    const fetch = mockApi()
    render(<App />)
    await screen.findByText('18 / 30')
    fireEvent.click(screen.getByRole('button', { name: 'Analysis' }))
    expect(await screen.findByText('18.67')).toBeTruthy()
    const request = fetch.mock.calls.find(([url]) => new URL(url).pathname.endsWith('/analysis'))[0]
    expect(new URL(request).searchParams.get('start')).toBe('0')
    expect(new URL(request).searchParams.get('end')).toBe('2')
    expect(screen.getByAltText(/Individuals chart for S01/).src).toContain('/api/charts/history.svg')
    expect(screen.getByText('These two charts follow the simulation day and time above.')).toBeTruthy()
    expect(screen.queryByText(/baseline|Review SPC/i)).toBeNull()
    expect(screen.getByRole('button', { name: /Play/ }).disabled).toBe(true)
  })
  it('plays one hourly slot every two seconds and pauses on workspace change', async () => {
    mockApi()
    render(<App />)
    await screen.findByText('18 / 30')
    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: /Play/ }))
    await act(async () => { vi.advanceTimersByTime(2000) })
    expect(screen.getByRole('slider', { name: 'Simulation time' }).value).toBe('3')
    fireEvent.click(screen.getByRole('button', { name: 'Analysis' }))
    await act(async () => { vi.advanceTimersByTime(4000) })
    expect(screen.getByRole('slider', { name: 'Simulation time' }).value).toBe('3')
    expect(screen.getByRole('slider', { name: 'Analysis end' }).value).toBe('2')
  })
  it('shows a readable upload error and lets the user recover with a demo source', async () => {
    mockApi({ uploadError: true })
    render(<App />)
    await screen.findByText('18 / 30')
    const file = new File(['timestamp,station_id,bikes'], 'invalid.csv', { type: 'text/csv' })
    fireEvent.change(screen.getByLabelText('Upload inventory CSV'), { target: { files: [file] } })
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('Duplicate station/timestamp rows are not allowed.'))
    fireEvent.click(screen.getByRole('button', { name: 'Use normal operations' }))
    expect(await screen.findByText('18 / 30')).toBeTruthy()
  })
})
