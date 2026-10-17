import { useRef } from 'react'
import './InventoryAlerts.css'

export default function InventoryAlerts({ alerts, loading, error, highlightedStation, onOpen, onDismiss, onHover, onFocus }) {
  const buttons = useRef(new Map())
  return <div className="inventory-alert-strip" role="region" aria-label="Station inventory alerts" aria-live="polite">
    {alerts.map((station, index) => <div key={`${station.station_id}-${station.status}`}
      className={`inventory-alert${highlightedStation === station.station_id ? ' linked-highlight' : ''}`}
      data-station={station.station_id}
      onMouseEnter={() => onHover(station.station_id)} onMouseLeave={() => onHover(null)}
      onFocus={() => onFocus(station.station_id)}
      onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) onFocus(null) }}>
      <button type="button" className="inventory-alert-open"
        ref={(element) => { if (element) buttons.current.set(station.station_id, element); else buttons.current.delete(station.station_id) }}
        aria-label={`${station.station_id} ${station.status}: ${station.display_name}. Open live chart`}
        onClick={() => onOpen(station.station_id)}>
        <span className="inventory-alert-icon" aria-hidden="true">!</span>
        <span><strong>{station.station_id} · {station.status === 'empty' ? 'Empty' : 'Full'}</strong>
          <span className="inventory-alert-name">{station.display_name}</span></span>
      </button>
      <button type="button" className="inventory-alert-dismiss" aria-label={`Dismiss ${station.status} alert for ${station.station_id}`}
        onClick={(event) => {
          event.stopPropagation()
          const next = alerts[index + 1] || alerts[index - 1]
          onHover(null)
          onFocus(null)
          onDismiss(station.station_id)
          if (next) buttons.current.get(next.station_id)?.focus()
        }}>×</button>
    </div>)}
    {!alerts.length && <p className="inventory-alert-empty">{loading ? 'Checking current station readings…'
      : error ? 'Current station alerts are unavailable.' : 'No active empty or full alerts.'}</p>}
  </div>
}
