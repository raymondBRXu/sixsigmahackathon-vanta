import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useResource } from './hooks.js'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

function deferred() {
  let resolve
  const promise = new Promise((finish) => { resolve = finish })
  return { promise, resolve }
}

describe('API request lifecycle', () => {
  it('aborts the old request and ignores a late response after the clock changes', async () => {
    const oldRequest = deferred()
    const newRequest = deferred()
    const fetch = vi.fn().mockReturnValueOnce(oldRequest.promise).mockReturnValueOnce(newRequest.promise)
    vi.stubGlobal('fetch', fetch)
    const { result, rerender } = renderHook(({ cursor }) => useResource('snapshot', { source: 'normal', cursor }), { initialProps: { cursor: 0 } })
    rerender({ cursor: 1 })
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(true)
    await act(async () => {
      newRequest.resolve({ ok: true, json: async () => ({ timestamp: 'new' }) })
    })
    expect(result.current.data.timestamp).toBe('new')
    await act(async () => {
      oldRequest.resolve({ ok: true, json: async () => ({ timestamp: 'old' }) })
    })
    expect(result.current.data.timestamp).toBe('new')
  })
  it('does not display a prior source snapshot while the new source is pending', async () => {
    const pending = deferred()
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ source: 'normal' }) })
      .mockReturnValueOnce(pending.promise))
    const { result, rerender } = renderHook(({ source }) => useResource('snapshot', { source, cursor: 1 }), { initialProps: { source: 'normal' } })
    await act(async () => {})
    expect(result.current.data.source).toBe('normal')
    rerender({ source: 'edge_cases' })
    expect(result.current.data).toBeNull()
  })
})
