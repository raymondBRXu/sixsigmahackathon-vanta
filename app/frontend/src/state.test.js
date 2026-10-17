import { describe, expect, it } from 'vitest'
import { dashboardReducer, initialState } from './state.js'

const dates = Array.from({ length: 40 }, (_, index) => new Date(Date.UTC(2026, 8, index + 3)).toISOString().slice(0, 10))
const hours = Array.from({ length: 15 }, (_, index) => index + 7)
const config = {
  source: { id: 'normal' }, default_cursor: 377,
  service_dates: dates, hours, timezone: 'America/New_York',
  timestamps: dates.flatMap((date) => hours.map((hour) => `${date}T${String(hour).padStart(2, '0')}:00:00-04:00`)),
  stations: [{ station_id: 'S01' }, { station_id: 'S20' }],
}
const ready = () => dashboardReducer(initialState, { type: 'sourceLoaded', config })

describe('dashboard navigation and playback', () => {
  it('opens a live station from an alert without changing the clock or playback', () => {
    const previous = { ...ready(), playing: true, historyStation: 'S01', diagnosis: true }
    const state = dashboardReducer(previous, { type: 'openRealtimeStation', station: 'S20' })
    expect(state).toMatchObject({ operationsView: 'View by Station', realtimeStation: 'S20', station: 'S20',
      cursor: previous.cursor, playing: true, historyStation: null, diagnosis: false })
    expect(dashboardReducer(state, { type: 'openRealtimeStation', station: 'S99' })).toBe(state)
    for (const action of [{ type: 'selectOperationsView', view: 'Overview' },
      { type: 'sourceRequested', source: 'disruption' }, { type: 'sourceLoaded', config }]) {
      expect(dashboardReducer(state, action).realtimeStation).toBeNull()
    }
  })
  it('locks the full history range for diagnosis until explicitly toggled off', () => {
    let state = dashboardReducer(ready(), { type: 'openHistory', station: 'S20' })
    expect(state.diagnosis).toBe(false)
    state = dashboardReducer(state, { type: 'setDateRange', dateRange: [20, 25] })
    state = dashboardReducer(state, { type: 'toggleDiagnosis' })
    expect(state).toMatchObject({ diagnosis: true, dateRange: [0, 39], historyStation: 'S20' })
    expect(dashboardReducer(state, { type: 'setDateRange', dateRange: [20, 25] })).toBe(state)
    state = dashboardReducer(state, { type: 'selectHour', hour: 17 })
    expect(state).toMatchObject({ diagnosis: true, dateRange: [0, 39], hour: 17 })
    state = dashboardReducer(state, { type: 'toggleDiagnosis' })
    state = dashboardReducer(state, { type: 'setDateRange', dateRange: [20, 25] })
    expect(state).toMatchObject({ diagnosis: false, dateRange: [20, 25] })
  })
  it('never carries diagnosis into another history dialog or source', () => {
    const state = { ...ready(), historyStation: 'S01', diagnosis: true }
    for (const action of [
      { type: 'closeHistory' }, { type: 'openHistory', station: 'S20' },
      { type: 'sourceRequested', source: 'disruption' }, { type: 'sourceLoaded', config },
      { type: 'selectOperationsView', view: 'Overview' },
    ]) expect(dashboardReducer(state, action).diagnosis).toBe(false)
    expect(dashboardReducer(ready(), { type: 'toggleDiagnosis' }).diagnosis).toBe(false)
  })
  it('switches between Overview and View by Station without resetting or pausing playback', () => {
    let state = { ...ready(), playing: true }
    expect(state.operationsView).toBe('Overview')
    state = dashboardReducer(state, { type: 'selectOperationsView', view: 'View by Station' })
    expect(state).toMatchObject({ operationsView: 'View by Station', cursor: 377, playing: true })
    state = dashboardReducer(state, { type: 'tick' })
    state = dashboardReducer(state, { type: 'selectOperationsView', view: 'Overview' })
    expect(state).toMatchObject({ operationsView: 'Overview', cursor: 378, playing: true })
  })
  it('starts at the demo time with no history dialog and the full configured date range', () => {
    expect(ready()).toMatchObject({ source: 'normal', cursor: 377, dateRange: [0, 39], hour: 7, playing: false, historyStation: null })
  })
  it('opens the clicked station history at 07:00 and the full range without changing sidebar station or cursor', () => {
    const previous = { ...ready(), station: 'S01', hour: 17, dateRange: [20, 25], cursor: 400, playing: true }
    let state = dashboardReducer(previous, { type: 'openHistory', station: 'S20' })
    expect(state).toMatchObject({ station: 'S01', historyStation: 'S20', hour: 7, dateRange: [0, 39], cursor: 400, playing: false })
    state = dashboardReducer(state, { type: 'selectHour', hour: 17 })
    state = dashboardReducer(state, { type: 'setDateRange', dateRange: [20, 25] })
    state = dashboardReducer(state, { type: 'closeHistory' })
    expect(state).toMatchObject({ historyStation: null, station: 'S01', cursor: 400, playing: false })
    state = dashboardReducer(state, { type: 'openHistory', station: 'S20' })
    expect(state).toMatchObject({ historyStation: 'S20', hour: 7, dateRange: [0, 39] })
  })
  it('rejects a History request for an unconfigured station', () => {
    const state = ready()
    expect(dashboardReducer(state, { type: 'openHistory', station: 'S99' })).toEqual(state)
  })
  it('uses the first configured hour when 07:00 is unavailable in History', () => {
    const state = { ...ready(), config: { ...config, hours: [9, 10, 11] }, hour: 11 }
    expect(dashboardReducer(state, { type: 'openHistory', station: 'S01' }).hour).toBe(9)
  })
  it('closes History when navigating or replacing its source', () => {
    const state = { ...ready(), historyStation: 'S20', playing: false }
    expect(dashboardReducer(state, { type: 'selectOperationsView', view: 'Overview' })).toMatchObject({ historyStation: null, operationsView: 'Overview', playing: false })
    expect(dashboardReducer(state, { type: 'sourceRequested', source: 'disruption' })).toMatchObject({ historyStation: null, source: 'disruption', loading: true })
    expect(dashboardReducer(state, { type: 'sourceLoaded', config })).toMatchObject({ historyStation: null, loading: false })
  })
  it('preserves a narrowed history range when playback rewinds before the selection', () => {
    const state = { ...ready(), dateRange: [24, 25], playing: true }
    expect(dashboardReducer(state, { type: 'setCursor', cursor: 345 })).toMatchObject({ cursor: 345, dateRange: [24, 25], playing: false })
  })
  it('retains the same date range when scrubbing earlier within the current day', () => {
    expect(dashboardReducer(ready(), { type: 'setCursor', cursor: 375 })).toMatchObject({ cursor: 375, dateRange: [0, 39] })
  })
  it('keeps the chosen range when stepping or playing across service days', () => {
    const state = { ...ready(), cursor: 389, dateRange: [27, 33], playing: true }
    expect(dashboardReducer(state, { type: 'tick' })).toMatchObject({ cursor: 390, dateRange: [27, 33], playing: true })
    expect(dashboardReducer(state, { type: 'step', direction: 1 })).toMatchObject({ cursor: 390, dateRange: [27, 33], playing: false })
    expect(dashboardReducer({ ...state, cursor: 390 }, { type: 'step', direction: -1 })).toMatchObject({ cursor: 389, dateRange: [27, 33], playing: false })
  })
  it('stops at the last available time', () => {
    const state = dashboardReducer({ ...ready(), cursor: 598, playing: true }, { type: 'tick' })
    expect(state).toMatchObject({ cursor: 599, playing: false })
    expect(dashboardReducer(state, { type: 'togglePlayback' }).playing).toBe(false)
  })
  it('pauses when the user selects a station, scrubs, steps, or opens History', () => {
    const playing = { ...ready(), playing: true }
    for (const action of [
      { type: 'selectStation', station: 'S20' }, { type: 'setCursor', cursor: 100 },
      { type: 'step', direction: 1 }, { type: 'openHistory', station: 'S20' },
    ]) expect(dashboardReducer(playing, action).playing).toBe(false)
  })
  it('never advances or enables playback while History is open', () => {
    const state = { ...ready(), historyStation: 'S20' }
    expect(dashboardReducer(state, { type: 'togglePlayback' }).playing).toBe(false)
    expect(dashboardReducer({ ...state, playing: true }, { type: 'tick' }).cursor).toBe(377)
  })
  it('resets clock and dates for a new source while preserving its valid sidebar station and hour', () => {
    const state = { ...ready(), cursor: 510, dateRange: [27, 33], hour: 17, station: 'S20', playing: true, historyStation: 'S01' }
    const changed = dashboardReducer(state, { type: 'sourceLoaded', config: { ...config, source: { id: 'disruption' } } })
    expect(changed).toMatchObject({ source: 'disruption', cursor: 377, dateRange: [0, 39], hour: 17, playing: false, station: 'S20', historyStation: null })
  })
  it('selects the first configured hour if the previous source hour is unavailable', () => {
    const changed = dashboardReducer(ready(), { type: 'sourceLoaded', config: { ...config, hours: [9, 10, 11] } })
    expect(changed.hour).toBe(9)
    expect(dashboardReducer(changed, { type: 'selectHour', hour: 7 }).hour).toBe(9)
  })
  it('keeps the date range ordered and inside the full configured service dates', () => {
    expect(dashboardReducer(ready(), { type: 'setDateRange', dateRange: [20, 39] }).dateRange).toEqual([20, 39])
    expect(dashboardReducer(ready(), { type: 'setDateRange', dateRange: [-3, 45] }).dateRange).toEqual([0, 39])
    expect(dashboardReducer(ready(), { type: 'setDateRange', dateRange: [45, 50] }).dateRange).toEqual([39, 39])
    expect(dashboardReducer(ready(), { type: 'setDateRange', dateRange: [20, 10] }).dateRange).toEqual([20, 20])
  })
  it('retains the full history range and late hours at the first playback snapshot', () => {
    const state = dashboardReducer(ready(), { type: 'setCursor', cursor: 0 })
    expect(state.dateRange).toEqual([0, 39])
    expect(dashboardReducer(state, { type: 'selectHour', hour: 21 }).hour).toBe(21)
    expect(dashboardReducer(state, { type: 'step', direction: -1 }).cursor).toBe(0)
  })
  it('supports a source with one configured service date', () => {
    const singleDate = { ...config, service_dates: [dates[0]], timestamps: config.timestamps.slice(0, hours.length), default_cursor: 0 }
    const state = dashboardReducer(ready(), { type: 'sourceLoaded', config: singleDate })
    expect(state).toMatchObject({ cursor: 0, dateRange: [0, 0] })
    expect(dashboardReducer(state, { type: 'setDateRange', dateRange: [-1, 4] }).dateRange).toEqual([0, 0])
  })
})
