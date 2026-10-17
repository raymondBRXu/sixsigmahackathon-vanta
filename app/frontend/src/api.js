const API_BASE = import.meta.env.VITE_API_BASE || './'

export function apiUrl(path, params = {}) {
  const base = new URL(API_BASE.endsWith('/') ? API_BASE : `${API_BASE}/`, document.baseURI)
  const url = new URL(`api/${path}`, base)
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) url.searchParams.set(key, value)
  })
  return url.toString()
}

export async function requestJson(path, { params, signal, body, method } = {}) {
  const response = await fetch(apiUrl(path, params), { signal, body, method })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    const detail = payload.detail
    const message = typeof detail === 'string' ? detail
      : Array.isArray(detail) ? detail.map((item) => item.msg).join('; ')
        : `Request failed (${response.status}). Please try again.`
    throw new Error(message)
  }
  return response.json()
}
