import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import stationData from '../../../../data/stations.json'
import RealtimeStations from './RealtimeStations.jsx'

const stations = stationData.map((station) => ({ ...station, display_name: station.name.replace(' — simulated station', '') }))
const observations = readFileSync(resolve(process.cwd(), '../../data/normal.csv'), 'utf8').trim().split('\n').slice(1).map((line) => {
  const [timestamp, station_id, bikes] = line.split(',')
  return { timestamp, station_id, bikes: Number(bikes) }
})
const timestamps = [...new Set(observations.map((row) => row.timestamp))]
const counts = new Map(observations.map((row) => [`${row.station_id}/${row.timestamp}`, row.bikes]))
const config = { stations, timestamps, timezone: 'America/New_York' }
const state = { config, source: 'normal', cursor: 0, playing: false }

function payload(cursor, overrides = {}) {
  const window = timestamps.slice(Math.max(0, cursor - 7), cursor + 1)
  return {
    timestamp: timestamps[cursor], window_size: 8, timestamps: window,
    reference_lines: { center: 15, upper: 24, lower: 6 },
    stations: stations.map((station) => ({
      station_id: station.station_id, display_name: station.display_name, capacity: station.capacity,
      history: window.map((timestamp, index) => ({ timestamp, bikes: overrides[station.station_id] ? overrides[station.station_id][index] : counts.get(`${station.station_id}/${timestamp}`) })),
    })),
  }
}

function response(data) {
  return { ok: true, json: async () => data }
}

function deferred() {
  let resolve
  const promise = new Promise((finish) => { resolve = finish })
  return { promise, resolve }
}

function mockPlayback() {
  const fetch = vi.fn(async (input) => response(payload(Number(new URL(input).searchParams.get('cursor')))))
  vi.stubGlobal('fetch', fetch)
  return fetch
}

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('realtime station charts', () => {
  it('fetches one batch and shows all 20 real station names in configuration order', async () => {
    const data = payload(7)
    data.stations.reverse()
    const fetch = vi.fn().mockResolvedValue(response(data))
    vi.stubGlobal('fetch', fetch)
    const { container } = render(<RealtimeStations state={{ ...state, cursor: 7, playing: true }} />)
    await waitFor(() => expect(container.querySelectorAll('.realtime-point')).toHaveLength(160))

    expect(fetch).toHaveBeenCalledTimes(1)
    const url = new URL(fetch.mock.calls[0][0])
    expect(url.pathname).toBe('/api/realtime')
    expect(Object.fromEntries(url.searchParams)).toEqual({ source: 'normal', cursor: '7' })
    const cards = screen.getAllByRole('article')
    expect(cards).toHaveLength(20)
    expect(cards.map((card) => card.querySelector('.realtime-station-id').textContent)).toEqual(stations.map((station) => station.station_id))
    cards.forEach((card, index) => {
      const name = stations[index].display_name
      expect(within(card).getByRole('heading', { name }).title).toBe(`${stations[index].station_id} · ${name}`)
      expect(within(card).getByRole('img', { name: `${stations[index].station_id} · ${name}: last eight scheduled bike readings` })).toBeTruthy()
      expect(card.querySelectorAll('.realtime-point')).toHaveLength(8)
    })
    expect(screen.getAllByText('CL 15')).toHaveLength(20)
    expect(screen.getAllByText('Upper 24')).toHaveLength(20)
    expect(screen.getAllByText('Lower 6')).toHaveLength(20)
    expect(screen.getByText('Playing simulation')).toBeTruthy()
    expect(screen.getByText(/Synthetic simulation playback/).textContent).toContain('Fixed inventory reference lines')
  })

  it('reserves eight fixed slots from the first observation and keeps geometry through rolling and rewind', async () => {
    const fetch = mockPlayback()
    const { rerender } = render(<RealtimeStations state={state} />)
    const card = screen.getAllByRole('article')[0]
    const chart = within(card).getByRole('img')
    await waitFor(() => expect(card.querySelectorAll('.realtime-point')).toHaveLength(1))
    const initialPoint = card.querySelector('.realtime-point')
    expect(initialPoint.getAttribute('cx')).toBe('292')
    expect(initialPoint.getAttribute('cy')).toBe('73')
    expect(card.querySelectorAll('.realtime-x-axis > g')).toHaveLength(8)
    expect(chart.getAttribute('viewBox')).toBe('0 0 306 171')
    const referenceCoordinates = () => [...card.querySelectorAll('.realtime-reference line')].map((line) => [line.getAttribute('y1'), line.getAttribute('y2')])
    const initialReferences = referenceCoordinates()
    expect(initialReferences).toEqual([['38.8', '38.8'], ['73', '73'], ['107.2', '107.2']])

    rerender(<RealtimeStations state={{ ...state, cursor: 7 }} />)
    expect(card.querySelectorAll('.realtime-point')).toHaveLength(0)
    await waitFor(() => expect(card.querySelectorAll('.realtime-point')).toHaveLength(8))
    const fullWindow = [...card.querySelectorAll('.realtime-point')].map((point) => point.getAttribute('data-timestamp'))
    expect(fullWindow).toEqual(timestamps.slice(0, 8))
    expect([...card.querySelectorAll('.realtime-point')].map((point) => Number(point.getAttribute('cx')))).toEqual([26, 64, 102, 140, 178, 216, 254, 292])

    rerender(<RealtimeStations state={{ ...state, cursor: 8 }} />)
    await waitFor(() => expect(card.querySelector('.realtime-point')?.getAttribute('data-timestamp')).toBe(timestamps[1]))
    expect([...card.querySelectorAll('.realtime-point')].map((point) => point.getAttribute('data-timestamp'))).toEqual(timestamps.slice(1, 9))
    expect(referenceCoordinates()).toEqual(initialReferences)
    expect(within(card).getByRole('img')).toBe(chart)
    expect(chart.getAttribute('width')).toBe('306')
    expect(chart.getAttribute('height')).toBe('171')

    rerender(<RealtimeStations state={state} />)
    await waitFor(() => expect(card.querySelectorAll('.realtime-point')).toHaveLength(1))
    expect(screen.getAllByRole('article')[0]).toBe(card)
    expect(card.querySelector('.realtime-point').getAttribute('cx')).toBe('292')
    expect(referenceCoordinates()).toEqual(initialReferences)
    expect(fetch).toHaveBeenCalledTimes(4)
  })

  it('plots true zero and thirty, leaves missing readings as gaps, and highlights only strict crossings', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(payload(7, { S01: [6, 24, 0, null, 30, 5, 25, null] }))))
    render(<RealtimeStations state={{ ...state, cursor: 7 }} />)
    const card = screen.getAllByRole('article')[0]
    await waitFor(() => expect(card.querySelectorAll('.realtime-point')).toHaveLength(6))
    const points = [...card.querySelectorAll('.realtime-point')]
    expect(points.map((point) => point.getAttribute('data-bikes'))).toEqual(['6', '24', '0', '30', '5', '25'])
    expect(points.map((point) => point.classList.contains('outside-reference'))).toEqual([false, false, true, true, true, true])
    expect(points[2].getAttribute('cy')).toBe('130')
    expect(points[3].getAttribute('cy')).toBe('16')
    const path = card.querySelector('.realtime-trace').getAttribute('d')
    expect(path).toBe('M26,107.2 L64,38.8 M64,38.8 L102,130 M178,16 L216,111 M216,111 L254,35')
    expect(card.querySelectorAll('.realtime-missing')).toHaveLength(2)
    expect(within(card).getByText('No reading')).toBeTruthy()
    expect(card.querySelector('time').dateTime).toBe(timestamps[7])
    expect(points[2].querySelector('title').textContent).toContain('S01 · Robert Purcell Community Center')
    expect(points[2].querySelector('title').textContent).toContain('0 bikes')
    expect(points[2].querySelector('title').textContent).toContain('Aug 24')
  })

  it('uses eight scheduled slots across service days without connecting overnight', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(payload(15))))
    render(<RealtimeStations state={{ ...state, cursor: 15 }} />)
    const card = screen.getAllByRole('article')[0]
    await waitFor(() => expect(card.querySelectorAll('.realtime-point')).toHaveLength(8))
    expect(card.querySelector('.realtime-trace').getAttribute('d').match(/L/g)).toHaveLength(6)
    expect([...card.querySelectorAll('.realtime-point')].map((point) => point.getAttribute('data-timestamp'))).toEqual(timestamps.slice(8, 16))
    expect(card.querySelector('.realtime-trace').getAttribute('d')).not.toContain('L292,')
    const ticks = [...card.querySelectorAll('.realtime-x-axis text')]
    expect(ticks[6].querySelector('title').textContent).toContain('Aug 24 · 21:00')
    expect(ticks[7].querySelector('title').textContent).toContain('Aug 25 · 07:00')
  })

  it('keeps station boxes while loading and on failure without retaining current points from another source', async () => {
    const pending = deferred()
    const fetch = vi.fn().mockResolvedValueOnce(response(payload(7))).mockReturnValueOnce(pending.promise)
    vi.stubGlobal('fetch', fetch)
    const { rerender } = render(<RealtimeStations state={{ ...state, cursor: 7 }} />)
    const card = screen.getAllByRole('article')[0]
    await waitFor(() => expect(card.querySelectorAll('.realtime-point')).toHaveLength(8))
    rerender(<RealtimeStations state={{ ...state, source: 'edge_cases', cursor: 7 }} />)
    expect(card.querySelectorAll('.realtime-point')).toHaveLength(0)
    expect(screen.getAllByRole('article')).toHaveLength(20)
    expect(screen.getByRole('status').textContent).toBe('Updating station readings…')
    expect(within(card).getByText('Updating…')).toBeTruthy()
    expect(card.querySelector('svg').getAttribute('viewBox')).toBe('0 0 306 171')
    await act(async () => {
      pending.resolve({ ok: false, status: 503, json: async () => ({ detail: 'Service unavailable' }) })
    })
    expect(screen.getByRole('alert').textContent).toContain('Service unavailable')
    expect(screen.getAllByRole('article')[0]).toBe(card)
    expect(within(card).getByText('Unavailable')).toBeTruthy()
    expect(card.querySelectorAll('.realtime-point')).toHaveLength(0)
    expect(card.querySelectorAll('.realtime-reference line')).toHaveLength(3)
  })

  it('ignores late source responses after a newer source has loaded', async () => {
    const oldRequest = deferred()
    const newRequest = deferred()
    const fetch = vi.fn().mockReturnValueOnce(oldRequest.promise).mockReturnValueOnce(newRequest.promise)
    vi.stubGlobal('fetch', fetch)
    const { rerender } = render(<RealtimeStations state={state} />)
    rerender(<RealtimeStations state={{ ...state, source: 'edge_cases' }} />)
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(true)
    const card = screen.getAllByRole('article')[0]
    await act(async () => { newRequest.resolve(response(payload(0, { S01: [30] }))) })
    expect(within(card).getByText('30 / 30 bikes')).toBeTruthy()
    await act(async () => { oldRequest.resolve(response(payload(0))) })
    expect(within(card).getByText('30 / 30 bikes')).toBeTruthy()
    expect(card.querySelector('.realtime-point').getAttribute('data-bikes')).toBe('30')
  })
})
