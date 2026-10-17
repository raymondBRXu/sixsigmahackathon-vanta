export const count = (value) => value === null || value === undefined ? '—' : Math.round(value).toString()
export const percent = (value) => value === null || value === undefined ? '—' : `${Math.round(value * 100)}%`
export const decimal = (value) => value === null || value === undefined ? '—' : value.toFixed(2)

export function formatTime(value, timezone, full = false) {
  if (!value) return 'No reading'
  const date = new Date(value)
  const day = new Intl.DateTimeFormat('en-US', {
    timeZone: timezone, month: 'short', day: '2-digit', ...(full ? { weekday: 'long' } : {}),
  }).format(date)
  const time = new Intl.DateTimeFormat('en-GB', {
    timeZone: timezone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).format(date)
  const zone = full ? ` ${new Intl.DateTimeFormat('en-US', {
    timeZone: timezone, timeZoneName: 'short',
  }).formatToParts(date).find((part) => part.type === 'timeZoneName').value}` : ''
  return `${day} · ${time}${zone}`
}

export const STATUS = {
  normal: { label: 'Available', color: '#258577' },
  low: { label: 'Low stock', color: '#db9d38' },
  high: { label: 'High stock', color: '#b87531' },
  empty: { label: 'Empty', color: '#ca5155' },
  full: { label: 'Full', color: '#7653a3' },
  missing: { label: 'Missing', color: '#9da5a6' },
  stale: { label: 'Stale', color: '#687680' },
}

export function moveLabel(value) {
  if (value === null || value === undefined) return 'Reinspect'
  return value > 0 ? `+${count(value)}` : count(value)
}
