import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import useInventoryAlerts from './useInventoryAlerts.js'

afterEach(cleanup)

const row = (station_id, status, bikes = status === 'empty' ? 0 : status === 'full' ? 30 : 15) => ({ station_id, status, bikes, display_name: `Station ${station_id}` })
const snapshot = (...stations) => ({ stations })
const initial = { source: 'normal', cursor: 10, data: snapshot(row('S01', 'empty'), row('S02', 'full')) }
const renderAlerts = () => renderHook(({ source, cursor, data }) => useInventoryAlerts(source, cursor, data), { initialProps: initial })
const ids = (result) => result.current.alerts.map((station) => station.station_id)

describe('continuous inventory alert conditions', () => {
  it('keeps station dismissals independent across the same and consecutive critical snapshots', () => {
    const { result, rerender } = renderAlerts()
    expect(ids(result)).toEqual(['S01', 'S02'])
    act(() => result.current.dismiss('S01'))
    expect(ids(result)).toEqual(['S02'])
    rerender({ ...initial, data: snapshot(row('S01', 'empty'), row('S02', 'full')) })
    expect(ids(result)).toEqual(['S02'])
    rerender({ ...initial, cursor: 11 })
    expect(ids(result)).toEqual(['S02'])
    act(() => result.current.dismiss('S02'))
    expect(ids(result)).toEqual([])
    rerender({ ...initial, cursor: 12 })
    expect(ids(result)).toEqual([])
  })

  it('shows a recovered station when its critical condition recurs without restoring another dismissed station', () => {
    const { result, rerender } = renderAlerts()
    act(() => { result.current.dismiss('S01'); result.current.dismiss('S02') })
    rerender({ ...initial, cursor: 11, data: snapshot(row('S01', 'normal'), row('S02', 'full')) })
    expect(ids(result)).toEqual([])
    rerender({ ...initial, cursor: 12 })
    expect(ids(result)).toEqual(['S01'])
    expect(result.current.alerts[0].status).toBe('empty')
  })

  it('treats empty-to-full and full-to-empty as new conditions', () => {
    const { result, rerender } = renderAlerts()
    act(() => result.current.dismiss('S01'))
    rerender({ ...initial, cursor: 11, data: snapshot(row('S01', 'full'), row('S02', 'normal')) })
    expect(result.current.alerts.map(({ station_id, status }) => [station_id, status])).toEqual([['S01', 'full']])
    act(() => result.current.dismiss('S01'))
    expect(ids(result)).toEqual([])
    rerender({ ...initial, cursor: 12, data: snapshot(row('S01', 'empty'), row('S02', 'normal')) })
    expect(result.current.alerts.map(({ station_id, status }) => [station_id, status])).toEqual([['S01', 'empty']])
  })

  it('hides alerts during loading and missing observations while preserving an unresolved dismissal', () => {
    const { result, rerender } = renderAlerts()
    act(() => result.current.dismiss('S01'))
    rerender({ ...initial, cursor: 11, data: null })
    expect(ids(result)).toEqual([])
    rerender({ ...initial, cursor: 11, data: snapshot(row('S01', 'stale', null), row('S02', 'missing', null)) })
    expect(ids(result)).toEqual([])
    rerender({ ...initial, cursor: 12, data: null })
    expect(ids(result)).toEqual([])
    rerender({ ...initial, cursor: 12 })
    expect(ids(result)).toEqual(['S02'])
    rerender({ ...initial, cursor: 13, data: snapshot(row('S01', 'normal'), row('S02', 'normal')) })
    rerender({ ...initial, cursor: 14 })
    expect(ids(result)).toEqual(['S01', 'S02'])
  })

  it('resets dismissals when changing source, even if the new source is still loading', () => {
    const { result, rerender } = renderAlerts()
    act(() => { result.current.dismiss('S01'); result.current.dismiss('S02') })
    rerender({ ...initial, source: 'disruption', data: null })
    expect(ids(result)).toEqual([])
    rerender({ ...initial, source: 'disruption' })
    expect(ids(result)).toEqual(['S01', 'S02'])
    act(() => result.current.dismiss('S01'))
    rerender({ ...initial, data: null })
    rerender(initial)
    expect(ids(result)).toEqual(['S01', 'S02'])
  })

  it.each([9, 12])('resets dismissed conditions when seeking directly from slot 10 to %i', (cursor) => {
    const { result, rerender } = renderAlerts()
    act(() => { result.current.dismiss('S01'); result.current.dismiss('S02') })
    rerender({ ...initial, cursor })
    expect(ids(result)).toEqual(['S01', 'S02'])
  })

  it('tracks pending cursor changes so a backward seek resets before its snapshot arrives', () => {
    const { result, rerender } = renderAlerts()
    act(() => { result.current.dismiss('S01'); result.current.dismiss('S02') })
    rerender({ ...initial, cursor: 11, data: null })
    expect(ids(result)).toEqual([])
    rerender({ ...initial, cursor: 10, data: null })
    expect(ids(result)).toEqual([])
    rerender(initial)
    expect(ids(result)).toEqual(['S01', 'S02'])
  })

  it('resets a forward seek while pending and preserves continuous dismissals across consecutive pending slots', () => {
    const { result, rerender } = renderAlerts()
    act(() => result.current.dismiss('S01'))
    rerender({ ...initial, cursor: 11, data: null })
    rerender({ ...initial, cursor: 12, data: null })
    rerender({ ...initial, cursor: 12 })
    expect(ids(result)).toEqual(['S02'])
    rerender({ ...initial, cursor: 20, data: null })
    rerender({ ...initial, cursor: 21, data: null })
    rerender({ ...initial, cursor: 21 })
    expect(ids(result)).toEqual(['S01', 'S02'])
  })

  it('requires a finite current critical reading and ignores dismissals of other stations', () => {
    const data = snapshot(row('S01', 'empty', null), row('S02', 'full', Number.NaN),
      row('S03', 'stale', 0), row('S04', 'low', 3), row('S05', 'high', 27), row('S06', 'empty', 0))
    const { result } = renderHook(() => useInventoryAlerts('normal', 0, data))
    expect(ids(result)).toEqual(['S06'])
    act(() => { result.current.dismiss('S01'); result.current.dismiss('S04'); result.current.dismiss('S99') })
    expect(ids(result)).toEqual(['S06'])
  })
})
