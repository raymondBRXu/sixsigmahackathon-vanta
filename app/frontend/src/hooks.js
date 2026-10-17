import { useEffect, useState } from 'react'
import { requestJson } from './api.js'

export function useResource(path, params, enabled = true) {
  const key = JSON.stringify(params)
  const [result, setResult] = useState({ key: '', data: null, error: '' })
  useEffect(() => {
    if (!enabled) return undefined
    const controller = new AbortController()
    requestJson(path, { params: JSON.parse(key), signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) setResult({ key, data, error: '' })
      })
      .catch((error) => {
        if (!controller.signal.aborted) setResult({ key, data: null, error: error.message })
      })
    return () => controller.abort()
  }, [path, key, enabled])
  return enabled && result.key === key ? result : { data: null, error: '' }
}
