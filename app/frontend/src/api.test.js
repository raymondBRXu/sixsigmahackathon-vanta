import { afterEach, describe, expect, it } from 'vitest'
import { apiUrl } from './api.js'

afterEach(() => document.querySelector('base')?.remove())

describe('deployment-relative API URLs', () => {
  it('keeps API and chart requests under a Posit Connect content prefix', () => {
    const base = document.createElement('base')
    base.href = 'https://example.test/content/dockwatch/'
    document.head.append(base)
    expect(apiUrl('snapshot', { source: 'normal', cursor: 377 })).toBe('https://example.test/content/dockwatch/api/snapshot?source=normal&cursor=377')
    expect(apiUrl('charts/history.svg', { source: 'normal', start: 0, end: 377 })).toContain('/content/dockwatch/api/charts/history.svg?')
  })
})
