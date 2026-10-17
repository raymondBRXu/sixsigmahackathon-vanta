import { afterEach, describe, expect, it } from 'vitest'
import { apiUrl } from './api.js'

afterEach(() => document.querySelector('base')?.remove())

describe('deployment-relative API URLs', () => {
  it('keeps API and chart requests under a Posit Connect content prefix', () => {
    const base = document.createElement('base')
    base.href = 'https://example.test/content/dockwatch/'
    document.head.append(base)
    expect(apiUrl('snapshot', { source: 'normal', cursor: 377 })).toBe('https://example.test/content/dockwatch/api/snapshot?source=normal&cursor=377')
    const chart = new URL(apiUrl('charts/history.svg', { source: 'normal', hour: 9, start_date: '2026-09-03', end_date: '2026-09-28' }))
    expect(chart.pathname).toBe('/content/dockwatch/api/charts/history.svg')
    expect(chart.searchParams.get('start_date')).toBe('2026-09-03')
  })
})
