import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import App from './App.jsx'

vi.mock('./components/StationMap.jsx', () => ({ default: () => <div aria-label="Station map" /> }))

// jsdom does not implement the native dialog lifecycle; focus and inertness are browser checks.
const dialogMethods = Object.fromEntries(['showModal', 'close'].map((name) => [name, Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name)]))
beforeAll(() => {
  Object.defineProperties(HTMLDialogElement.prototype, {
    showModal: { configurable: true, value() { this.setAttribute('open', '') } },
    close: { configurable: true, value() { this.removeAttribute('open'); this.dispatchEvent(new Event('close')) } },
  })
})
afterAll(() => {
  for (const [name, descriptor] of Object.entries(dialogMethods)) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor)
    else delete HTMLDialogElement.prototype[name]
  }
})

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers() })

const hours = [7, 8, 9, 10, 11]
const timestamps = hours.map((hour) => `2026-09-28T${String(hour).padStart(2, '0')}:00:00-04:00`)
const stations = [
  { station_id: 'S01', display_name: 'Robert Purcell Community Center', capacity: 30 },
  { station_id: 'S02', display_name: 'Appel Commons', capacity: 30 },
]
const scenarios = [{ id: 'normal', label: 'Normal operations' }, { id: 'edge_cases', label: 'Edge cases' }]

function mockApi({ missing = false, uploadError = false, configOverrides = {}, summary } = {}) {
  const config = (source) => ({ source: { id: source, label: `${source}.csv`, observations: 10 }, timestamps,
    service_dates: ['2026-09-28'], hours, timezone: 'America/New_York', stations, scenarios, default_cursor: 2, ...configOverrides })
  const rows = stations.map((station, index) => ({
    ...station, bikes: index === 0 ? missing ? null : 18 : 0, free_docks: index === 0 ? missing ? null : 12 : 30,
    status: index === 0 ? missing ? 'stale' : 'normal' : 'empty', net_change: null,
    latest_bikes: 18, latest_timestamp: timestamps[1], age_minutes: 60,
    suggested_change: index === 0 ? missing ? null : 0 : 15,
  }))
  const fetch = vi.fn(async (url) => {
    const request = new URL(url)
    if (request.pathname.endsWith('/uploads') && uploadError) return { ok: false, status: 422, json: async () => ({ detail: 'Duplicate station/timestamp rows are not allowed.' }) }
    if (request.pathname.endsWith('/realtime')) {
      const sourceConfig = config(request.searchParams.get('source'))
      const cursor = Number(request.searchParams.get('cursor'))
      const window = sourceConfig.timestamps.slice(Math.max(0, cursor - 7), cursor + 1)
      return { ok: true, json: async () => ({
        timestamp: sourceConfig.timestamps[cursor], window_size: 8, timestamps: window,
        reference_lines: { center: 15, upper: 24, lower: 6 },
        stations: sourceConfig.stations.map((station) => ({ ...station,
          history: window.map((timestamp) => ({ timestamp, bikes: station.station_id === 'S01' && missing ? null : 15 })),
        })),
      }) }
    }
    const payload = request.pathname.endsWith('/config') ? config(request.searchParams.get('source'))
      : request.pathname.endsWith('/snapshot') ? {
        stations: rows, queue: rows.filter((row) => row.status !== 'normal'),
        metrics: { availability: missing ? 0 : 0.5, available_count: missing ? 0 : 1, empty_count: 1, full_count: 0, n: missing ? 1 : 2, planned: 2, empty_rate: missing ? 1 : 0.5, full_rate: 0, coverage: missing ? 0.5 : 1 },
      } : {
        summary: summary || { n: 3, planned: 3, pairs: 2, cl: 18.67, limits: { lcl: 13.35, ucl: 23.99, mr_mean: 2, sigma: 1.773 }, reason: '' },
      }
    return { ok: true, json: async () => payload }
  })
  vi.stubGlobal('fetch', fetch)
  return fetch
}

function lastAnalysisParams(fetch) {
  const [url] = fetch.mock.calls.findLast(([url]) => new URL(url).pathname.endsWith('/analysis')) || []
  return url ? Object.fromEntries(new URL(url).searchParams) : {}
}

function lastRealtimeParams(fetch) {
  const [url] = fetch.mock.calls.findLast(([url]) => new URL(url).pathname.endsWith('/realtime')) || []
  return url ? Object.fromEntries(new URL(url).searchParams) : {}
}

const serviceDates = ['2026-09-28', '2026-09-29', '2026-09-30']
const multiDayConfig = {
  service_dates: serviceDates, default_cursor: 7,
  timestamps: serviceDates.flatMap((date) => hours.map((hour) => `${date}T${String(hour).padStart(2, '0')}:00:00-04:00`)),
}

async function openStationHistory(station = 'S01') {
  fireEvent.click(screen.getByRole('button', { name: 'View by Station' }))
  await screen.findByRole('region', { name: 'View by Station' })
  fireEvent.click(screen.getByRole('button', { name: new RegExp(`^History for ${station} ·`) }))
  return screen.findByRole('dialog', { name: 'Station history' })
}

describe('dashboard end-to-end component wiring', () => {
  it('opens all station charts and follows stepping, rewinding and source changes without old workspace tabs', async () => {
    const allStations = Array.from({ length: 20 }, (_, index) => ({
      station_id: `S${String(index + 1).padStart(2, '0')}`, display_name: `Station ${index + 1}`, capacity: 30,
    }))
    const fetch = mockApi({ configOverrides: { ...multiDayConfig, stations: allStations } })
    render(<App />)
    await screen.findByText('18 / 30')
    expect(lastRealtimeParams(fetch)).toEqual({})
    expect(screen.queryByRole('button', { name: 'Operations' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Analysis' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Realtime View by Station' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'View by Station' }))
    await waitFor(() => expect(lastRealtimeParams(fetch)).toEqual({ source: 'normal', cursor: '7' }))
    const realtime = screen.getByRole('region', { name: 'View by Station' })
    await waitFor(() => expect(within(realtime).getAllByRole('img')).toHaveLength(20))
    expect(within(realtime).getAllByRole('button', { name: /^History for / })).toHaveLength(20)
    expect(within(realtime).getAllByText('History')).toHaveLength(20)
    expect(screen.queryByLabelText('Station map')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Step →' }))
    await waitFor(() => expect(lastRealtimeParams(fetch).cursor).toBe('8'))
    fireEvent.change(screen.getByRole('slider', { name: 'Simulation time' }), { target: { value: '0' } })
    await waitFor(() => expect(lastRealtimeParams(fetch).cursor).toBe('0'))
    fireEvent.change(screen.getByLabelText('Demo scenario'), { target: { value: 'edge_cases' } })
    await waitFor(() => expect(lastRealtimeParams(fetch)).toEqual({ source: 'edge_cases', cursor: '7' }))
    fireEvent.click(screen.getByRole('button', { name: 'Overview' }))
    expect(screen.getByLabelText('Station map')).toBeTruthy()
    expect(screen.getByRole('slider', { name: 'Simulation time' }).value).toBe('7')
  })

  it('streams hourly updates, pauses for History and keeps its cursor when the dialog closes', async () => {
    const fetch = mockApi({ configOverrides: multiDayConfig })
    render(<App />)
    await screen.findByText('18 / 30')
    fireEvent.click(screen.getByRole('button', { name: 'View by Station' }))
    await waitFor(() => expect(lastRealtimeParams(fetch).cursor).toBe('7'))
    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: /Play/ }))
    await act(async () => { vi.advanceTimersByTime(2000) })
    expect(lastRealtimeParams(fetch).cursor).toBe('8')
    expect(screen.getByRole('button', { name: /Pause/ })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /^History for S02 ·/ }))
    await act(async () => { vi.advanceTimersByTime(4000) })
    expect(screen.getByRole('dialog', { name: 'Station history' })).toBeTruthy()
    expect(lastAnalysisParams(fetch)).toMatchObject({ station_id: 'S02', hour: '7', cursor: '14' })
    expect(lastRealtimeParams(fetch).cursor).toBe('8')
    expect(screen.getByRole('button', { name: /Play/ }).disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Close history' }))
    await act(async () => { vi.advanceTimersByTime(4000) })
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.getByRole('slider', { name: 'Simulation time' }).value).toBe('8')
    expect(screen.getByRole('button', { name: /Play/ }).disabled).toBe(false)
    expect(screen.getAllByRole('article')).toHaveLength(2)
    expect(screen.queryByRole('button', { name: /Back to all stations/ })).toBeNull()
  })

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

  it('opens the clicked station at 07:00 with matching Python metrics and chart parameters', async () => {
    const fetch = mockApi()
    render(<App />)
    await screen.findByText('18 / 30')
    expect(screen.getByLabelText('Station').value).toBe('S01')
    const dialog = await openStationHistory('S02')
    expect(await within(dialog).findByText('18.67')).toBeTruthy()
    expect(lastAnalysisParams(fetch)).toEqual({ source: 'normal', cursor: '4', station_id: 'S02', hour: '7', start_date: '2026-09-28', end_date: '2026-09-28' })
    const history = new URL(within(dialog).getByAltText(/Individuals chart for S02 at 07:00/).src)
    expect(history.pathname).toBe('/api/charts/history.svg')
    expect(Object.fromEntries(history.searchParams)).toEqual(lastAnalysisParams(fetch))
    expect(within(dialog).getByText(/2 consecutive service-date pairs at 07:00/)).toBeTruthy()
    expect(within(dialog).getByText('13.35')).toBeTruthy()
    expect(within(dialog).getByText('23.99')).toBeTruthy()
    expect(within(dialog).getAllByRole('img')).toHaveLength(1)
    expect(within(dialog).queryByAltText(/Latest-day inventory|Occupancy heatmap/)).toBeNull()
    expect(within(dialog).queryByRole('region', { name: 'Simulation playback' })).toBeNull()
    expect(within(dialog).queryByText(/baseline|Review SPC/i)).toBeNull()
    expect(screen.getByLabelText('Station').value).toBe('S01')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Close history' }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.queryByRole('button', { name: /Back to all stations/ })).toBeNull()
    expect(screen.getAllByRole('article')).toHaveLength(2)
    expect(screen.getByRole('slider', { name: 'Simulation time' }).value).toBe('2')
  })

  it('defaults to all service dates and includes final-day late hours independently of playback', async () => {
    const fetch = mockApi({ configOverrides: multiDayConfig })
    render(<App />)
    await screen.findByText('18 / 30')
    expect(screen.getByRole('slider', { name: 'Simulation time' }).value).toBe('7')
    const dialog = await openStationHistory()
    await within(dialog).findByText('18.67')
    expect(within(dialog).getByRole('slider', { name: 'Analysis start date' }).value).toBe('0')
    expect(within(dialog).getByRole('slider', { name: 'Analysis end date' }).value).toBe('2')
    expect(within(dialog).getByRole('slider', { name: 'Analysis end date' }).max).toBe('2')
    expect(within(dialog).getByLabelText('End date').options).toHaveLength(3)
    expect(lastAnalysisParams(fetch)).toEqual({ source: 'normal', cursor: '14', station_id: 'S01', hour: '7', start_date: '2026-09-28', end_date: '2026-09-30' })
    fireEvent.change(within(dialog).getByLabelText('Operating hour'), { target: { value: '11' } })
    await waitFor(() => expect(lastAnalysisParams(fetch)).toMatchObject({ cursor: '14', hour: '11', end_date: '2026-09-30' }))
    const history = within(dialog).getByAltText(/Individuals chart for S01 at 11:00/)
    expect(Object.fromEntries(new URL(history.src).searchParams)).toEqual(lastAnalysisParams(fetch))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Close history' }))
    expect(screen.getByRole('slider', { name: 'Simulation time' }).value).toBe('7')
  })

  it('updates hour and dates within History and restores 07:00 and the full range on each opening', async () => {
    const fetch = mockApi({ configOverrides: multiDayConfig })
    render(<App />)
    await screen.findByText('18 / 30')
    const dialog = await openStationHistory('S02')
    await within(dialog).findByText('18.67')
    fireEvent.change(within(dialog).getByLabelText('Operating hour'), { target: { value: '9' } })
    fireEvent.change(within(dialog).getByLabelText('Start date'), { target: { value: '1' } })
    fireEvent.change(within(dialog).getByRole('slider', { name: 'Analysis end date' }), { target: { value: '1' } })
    await waitFor(() => expect(lastAnalysisParams(fetch)).toEqual({ source: 'normal', cursor: '14', station_id: 'S02', hour: '9', start_date: '2026-09-29', end_date: '2026-09-29' }))
    const history = within(dialog).getByAltText(/Individuals chart for S02 at 09:00/)
    expect(Object.fromEntries(new URL(history.src).searchParams)).toEqual(lastAnalysisParams(fetch))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Close history' }))
    fireEvent.change(screen.getByRole('slider', { name: 'Simulation time' }), { target: { value: '0' } })
    fireEvent.click(screen.getByRole('button', { name: /^History for S02 ·/ }))
    await waitFor(() => expect(lastAnalysisParams(fetch)).toEqual({ source: 'normal', cursor: '14', station_id: 'S02', hour: '7', start_date: '2026-09-28', end_date: '2026-09-30' }))
    expect(screen.getByLabelText('Operating hour').value).toBe('7')
    expect(screen.getByLabelText('Start date').value).toBe('0')
    expect(screen.getByLabelText('End date').value).toBe('2')
    fireEvent.click(screen.getByRole('button', { name: 'Close history' }))
    fireEvent.click(screen.getByRole('button', { name: /^History for S01 ·/ }))
    await waitFor(() => expect(lastAnalysisParams(fetch)).toMatchObject({ station_id: 'S01', hour: '7' }))
    expect(screen.getByLabelText('Station').value).toBe('S01')
    expect(screen.getByRole('slider', { name: 'Simulation time' }).value).toBe('0')
  })

  it('cleans up History on a source change and uses the new full dataset when reopened', async () => {
    const fetch = mockApi({ configOverrides: multiDayConfig })
    render(<App />)
    await screen.findByText('18 / 30')
    const dialog = await openStationHistory('S02')
    await within(dialog).findByText('18.67')
    fireEvent.change(within(dialog).getByLabelText('Start date'), { target: { value: '2' } })
    fireEvent.change(within(dialog).getByLabelText('Operating hour'), { target: { value: '11' } })
    await waitFor(() => expect(lastAnalysisParams(fetch)).toMatchObject({ station_id: 'S02', hour: '11', start_date: '2026-09-30' }))
    // A source replacement can also be requested outside the modal's DOM lifecycle.
    fireEvent.change(screen.getByLabelText('Demo scenario'), { target: { value: 'edge_cases' } })
    await waitFor(() => expect(lastRealtimeParams(fetch)).toEqual({ source: 'edge_cases', cursor: '7' }))
    expect(screen.queryByRole('dialog')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /^History for S02 ·/ }))
    await waitFor(() => expect(lastAnalysisParams(fetch)).toEqual({ source: 'edge_cases', cursor: '14', station_id: 'S02', hour: '7', start_date: '2026-09-28', end_date: '2026-09-30' }))
    expect(screen.getByRole('slider', { name: 'Analysis start date' }).value).toBe('0')
    expect(screen.getByRole('slider', { name: 'Analysis end date' }).value).toBe('2')
    expect(screen.getByLabelText('Station').value).toBe('S01')
    expect(screen.getByRole('slider', { name: 'Simulation time' }).value).toBe('7')
  })

  it('closes History with a native cancel without also closing an enlarged realtime chart', async () => {
    mockApi({ configOverrides: multiDayConfig })
    render(<App />)
    await screen.findByText('18 / 30')
    fireEvent.click(screen.getByRole('button', { name: 'View by Station' }))
    const chart = screen.getByRole('img', { name: /^S02 · Appel Commons:/ })
    fireEvent.keyDown(chart, { key: 'Enter' })
    expect(screen.getAllByRole('article')).toHaveLength(1)
    const historyButton = screen.getByRole('button', { name: /^History for S02 ·/ })
    fireEvent.click(historyButton)
    const dialog = await screen.findByRole('dialog', { name: 'Station history' })
    await within(dialog).findByText('18.67')
    fireEvent.keyDown(within(dialog).getByRole('button', { name: 'Close history' }), { key: 'Escape' })
    expect(screen.getAllByRole('article')).toHaveLength(1)
    fireEvent(dialog, new Event('cancel', { cancelable: true }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.getAllByRole('article')).toHaveLength(1)
    expect(document.activeElement).toBe(historyButton)
    fireEvent.keyDown(screen.getByRole('button', { name: /Back to all stations/ }), { key: 'Escape' })
    expect(screen.getAllByRole('article')).toHaveLength(2)
    expect(screen.getByRole('slider', { name: 'Simulation time' }).value).toBe('7')
  })

  it.each([
    { name: 'no elapsed selected-hour readings', n: 0, planned: 0, pairs: 0, cl: null, limits: null, reason: 'No selected-hour observations have elapsed.' },
    { name: 'one reading', n: 1, planned: 1, pairs: 0, cl: 14, limits: null, reason: 'At least one consecutive service-date pair is required.' },
    { name: 'constant readings', n: 3, planned: 3, pairs: 2, cl: 14, limits: null, reason: 'Moving-range variation is zero.' },
  ])('shows the chart and backend explanation for $name', async (summary) => {
    mockApi({ summary })
    render(<App />)
    await screen.findByText('18 / 30')
    const dialog = await openStationHistory()
    expect(await within(dialog).findByText(summary.reason)).toBeTruthy()
    expect(within(dialog).getByText(`${summary.n} / ${summary.planned}`)).toBeTruthy()
    expect(within(dialog).getByAltText(/Individuals chart for S01/)).toBeTruthy()
    const center = within(dialog).getByText('Center line').closest('.metric')
    expect(within(center).getByText(summary.cl === null ? '—' : '14.00')).toBeTruthy()
    expect(within(within(dialog).getByText('LCL').closest('.metric')).getByText('—')).toBeTruthy()
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
