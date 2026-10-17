import { describe, expect, it } from 'vitest'
import { dashboardReducer, initialState } from './state.js'

const config = {
  source: { id: 'normal' }, default_cursor: 377,
  timestamps: Array.from({ length: 600 }, (_, index) => index),
  stations: [{ station_id: 'S01' }, { station_id: 'S20' }],
}
const ready = () => dashboardReducer(initialState, { type: 'sourceLoaded', config })

describe('dashboard navigation and playback', () => {
  it('starts at the historical normal demo time and includes all elapsed readings', () => {
    expect(ready()).toMatchObject({ source: 'normal', cursor: 377, interval: [0, 377], playing: false })
  })
  it('preserves the chosen interval across workspace and station changes', () => {
    let state = dashboardReducer(ready(), { type: 'setInterval', interval: [375, 377] })
    state = dashboardReducer(state, { type: 'selectView', view: 'Analysis' })
    state = dashboardReducer(state, { type: 'selectStation', station: 'S20' })
    state = dashboardReducer(state, { type: 'selectView', view: 'Operations' })
    expect(state).toMatchObject({ interval: [375, 377], station: 'S20' })
  })
  it('clamps both interval ends when the clock moves back before the selection', () => {
    const state = { ...ready(), interval: [370, 375], playing: true }
    expect(dashboardReducer(state, { type: 'setCursor', cursor: 360 })).toMatchObject({ cursor: 360, interval: [360, 360], playing: false })
  })
  it('does not extend the interval when playback advances', () => {
    const state = dashboardReducer({ ...ready(), playing: true }, { type: 'tick' })
    expect(state).toMatchObject({ cursor: 378, interval: [0, 377], playing: true })
  })
  it('stops at the last available time', () => {
    const state = dashboardReducer({ ...ready(), cursor: 598, playing: true }, { type: 'tick' })
    expect(state).toMatchObject({ cursor: 599, playing: false })
    expect(dashboardReducer(state, { type: 'togglePlayback' }).playing).toBe(false)
  })
  it('pauses when the user selects a station, scrubs, steps, or opens Analysis', () => {
    const playing = { ...ready(), playing: true }
    for (const action of [
      { type: 'selectStation', station: 'S20' }, { type: 'setCursor', cursor: 100 },
      { type: 'step', direction: 1 }, { type: 'selectView', view: 'Analysis' },
    ]) expect(dashboardReducer(playing, action).playing).toBe(false)
  })
  it('never advances or enables playback in Analysis', () => {
    const state = { ...ready(), view: 'Analysis' }
    expect(dashboardReducer(state, { type: 'togglePlayback' }).playing).toBe(false)
    expect(dashboardReducer({ ...state, playing: true }, { type: 'tick' }).cursor).toBe(377)
  })
  it('resets time and range when a different data source is loaded', () => {
    const state = { ...ready(), cursor: 510, interval: [400, 500], station: 'S20', playing: true }
    const changed = dashboardReducer(state, { type: 'sourceLoaded', config: { ...config, source: { id: 'edge_cases' } } })
    expect(changed).toMatchObject({ source: 'edge_cases', cursor: 377, interval: [0, 377], playing: false, station: 'S20' })
  })
  it('keeps range ordered and inside elapsed timestamps', () => {
    expect(dashboardReducer(ready(), { type: 'setInterval', interval: [300, 599] }).interval).toEqual([300, 377])
    expect(dashboardReducer(ready(), { type: 'setInterval', interval: [300, 100] }).interval).toEqual([300, 300])
  })
  it('permits a one-reading interval at the first snapshot', () => {
    const state = dashboardReducer(ready(), { type: 'setCursor', cursor: 0 })
    expect(state.interval).toEqual([0, 0])
    expect(dashboardReducer(state, { type: 'step', direction: -1 }).cursor).toBe(0)
  })
})
