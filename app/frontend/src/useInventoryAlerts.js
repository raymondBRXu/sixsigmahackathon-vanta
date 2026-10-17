import { useEffect, useState } from 'react'

const isCritical = (row) => Number.isFinite(row.bikes) && ['empty', 'full'].includes(row.status)

function reconcile(previous, source, cursor, snapshot) {
  const continuous = previous.source === source && (cursor === previous.cursor || cursor === previous.cursor + 1)
  let dismissed = continuous ? previous.dismissed : {}
  if (snapshot) {
    const stations = new Map(snapshot.stations.map((row) => [row.station_id, row]))
    dismissed = Object.fromEntries(Object.entries(dismissed).filter(([id, status]) => {
      const row = stations.get(id)
      // Missing readings are not evidence that a dismissed condition recovered.
      return row && (!Number.isFinite(row.bikes) || row.status === status)
    }))
  }
  if (source === previous.source && cursor === previous.cursor
    && JSON.stringify(dismissed) === JSON.stringify(previous.dismissed)) return previous
  return { source, cursor, dismissed }
}

export default function useInventoryAlerts(source, cursor, snapshot) {
  const [memory, setMemory] = useState({ source, cursor, dismissed: {} })
  // Reconcile during rendering as well, so a new snapshot never flashes old alerts.
  const current = reconcile(memory, source, cursor, snapshot)
  useEffect(() => {
    setMemory((previous) => reconcile(previous, source, cursor, snapshot))
  }, [source, cursor, snapshot])

  const alerts = (snapshot?.stations || []).filter((row) => isCritical(row)
    && current.dismissed[row.station_id] !== row.status)

  function dismiss(stationId) {
    const row = snapshot?.stations.find((station) => station.station_id === stationId)
    if (!row || !isCritical(row)) return
    setMemory((previous) => {
      const next = reconcile(previous, source, cursor, snapshot)
      return { ...next, dismissed: { ...next.dismissed, [stationId]: row.status } }
    })
  }

  return { alerts, dismiss }
}
