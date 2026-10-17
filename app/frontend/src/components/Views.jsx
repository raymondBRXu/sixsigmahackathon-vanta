import { useEffect, useState } from 'react'
import { apiUrl } from '../api.js'
import { useResource } from '../hooks.js'
import { count, decimal, formatHour, formatTime, percent, STATUS } from '../format.js'
import { DateRangeSlider } from './Controls.jsx'
import StationMap from './StationMap.jsx'
import HistoryChart from './HistoryChart.jsx'
import InventoryAlerts from './InventoryAlerts.jsx'

export function Metric({ label, value, detail }) {
  return <div className="metric"><span className="metric-label">{label}</span><strong>{value}</strong>{detail && <span className="metric-detail">{detail}</span>}</div>
}

export function StatusBadge({ status }) {
  return <span className="status-badge" style={{ '--status-color': STATUS[status].color }}><i />{STATUS[status].label}</span>
}

export function Operations({ state, dispatch, camera, snapshot, inventoryAlerts }) {
  const { source, cursor, station, config, tiles } = state
  const { data, error } = snapshot
  const [hovered, setHovered] = useState(null)
  const [focused, setFocused] = useState(null)
  const selectionKey = `${source}:${cursor}`
  useEffect(() => {
    setHovered(null)
    setFocused(null)
  }, [selectionKey])
  const highlight = data ? (hovered?.key === selectionKey ? hovered.station
    : focused?.key === selectionKey ? focused.station : null) : null
  const onHover = (id) => setHovered(id ? { key: selectionKey, station: id } : null)
  const onFocus = (id) => setFocused(id ? { key: selectionKey, station: id } : null)
  const metrics = data?.metrics
  const selected = data?.stations.find((row) => row.station_id === station)
  return <section aria-label="Operations overview" aria-busy={!data && !error}>
    {error && <p className="error-banner" role="alert">{error}</p>}
    <div className="metric-grid">
      <Metric label="Two-way availability" value={percent(metrics?.availability)} detail={metrics && `${metrics.available_count} of ${metrics.n} observed stations`} />
      <Metric label="Empty stations" value={count(metrics?.empty_count)} detail={metrics && `${percent(metrics.empty_rate)} · no bikes to borrow`} />
      <Metric label="Full stations" value={count(metrics?.full_count)} detail={metrics && `${percent(metrics.full_rate)} · no docks to return`} />
      <Metric label="Observation coverage" value={percent(metrics?.coverage)} detail={metrics && `${metrics.n} / ${metrics.planned} planned stations`} />
    </div>
    <div className="operations-grid">
      <div className="map-panel">
        <InventoryAlerts alerts={inventoryAlerts.alerts} loading={!data && !error} error={error}
          highlightedStation={highlight} onHover={onHover} onFocus={onFocus}
          onDismiss={inventoryAlerts.dismiss}
          onOpen={(id) => dispatch({ type: 'openRealtimeStation', station: id })} />
        <p className="caption">Hover an alert, queue row or map point to locate its station. Select an alert to open its live chart.</p>
        <div className="map-shell">
          <StationMap stations={data?.stations || []} selected={station} tiles={tiles}
            highlightedStation={highlight} onHoverStation={onHover} onFocusStation={onFocus}
            timezone={config.timezone} camera={camera}
            onSelect={(id) => dispatch({ type: 'selectStation', station: id })} />
          {!data && !error && <div className="map-loading" role="status">Loading snapshot…</div>}
        </div>
      </div>
      <div className="queue-panel">
        <h2>Action queue</h2>
        <p className="caption">Empty / full first, then low / high stock. Hover or focus a row to locate its station.</p>
        {data && (data.queue.length ? <div className="queue-scroll">
          <table className="queue-table">
            <caption className="sr-only">Current station inventory actions</caption>
            <thead><tr><th>Station</th><th>Bikes</th><th>State</th></tr></thead>
            <tbody>{data.queue.map((row) => <tr key={row.station_id} tabIndex={0} data-station={row.station_id}
              className={highlight === row.station_id ? 'linked-highlight' : ''}
              aria-label={`${row.station_id} · ${row.display_name}: ${count(row.bikes)} bikes, ${STATUS[row.status].label}`}
              onMouseEnter={() => onHover(row.station_id)} onMouseLeave={() => onHover(null)}
              onFocus={() => onFocus(row.station_id)} onBlur={() => onFocus(null)}>
              <td><strong>{row.station_id}</strong><span className="queue-station-name">{row.display_name}</span></td>
              <td>{count(row.bikes)}</td><td><StatusBadge status={row.status} /></td>
            </tr>)}</tbody>
          </table>
        </div> : <div className="success-message"><span aria-hidden="true">✓</span> No current inventory threshold actions.</div>)}
        {!data && !error && <div className="queue-placeholder" aria-hidden="true" />}
      </div>
    </div>
    <div className="station-detail">
      <div className="station-detail-heading">
        <h3>{station} · {config.stations.find((row) => row.station_id === station).display_name}</h3>
        {selected && <StatusBadge status={selected.status} />}
      </div>
      <div className="detail-metrics">
        <Metric label="Current bikes" value={selected ? `${count(selected.bikes)} / ${selected.capacity}` : '—'} />
        <Metric label="Free docks" value={count(selected?.free_docks)} />
        <Metric label="Hourly net change" value={count(selected?.net_change)} />
      </div>
      {selected?.bikes === null && <p className="caption">Last reading: {count(selected.latest_bikes)} bikes · {formatTime(selected.latest_timestamp, config.timezone, true)} · age {count(selected.age_minutes)} minutes. Excluded from current metrics.</p>}
    </div>
    <a className="button download-button" href={apiUrl('snapshot.csv', { source, cursor })} download><span aria-hidden="true">↓</span> Download current snapshot</a>
  </section>
}

export function StationHistory({ state, dispatch }) {
  const { source, historyStation: station, dateRange, hour, config, diagnosis } = state
  const cursor = config.timestamps.length - 1
  const params = { source, cursor, station_id: station, hour,
    start_date: config.service_dates[dateRange[0]], end_date: config.service_dates[dateRange[1]],
    ...(diagnosis ? { diagnosis: true } : {}) }
  const key = JSON.stringify(params)
  const [settledKey, setSettledKey] = useState(key)
  useEffect(() => {
    const timer = setTimeout(() => setSettledKey(key), 180)
    return () => clearTimeout(timer)
  }, [key])
  const settledParams = JSON.parse(settledKey)
  const { data, error } = useResource('analysis', settledParams, key === settledKey)
  const summary = data?.summary
  const limits = summary?.limits
  return <section aria-label="Individuals chart history">
    <div className="analysis-heading">
      <h2>{station} · {config.stations.find((row) => row.station_id === station).display_name}</h2>
      <p className="caption">Compare this station at the same operating hour across service dates. Hover a point to inspect its reading. Enable Diagnosis to check all dates for eight unusual patterns.</p>
    </div>
    <div className="hour-selector">
      <label htmlFor="analysis-hour">Operating hour</label>
      <select id="analysis-hour" value={hour} onChange={(event) => dispatch({ type: 'selectHour', hour: Number(event.target.value) })}>
        {config.hours.map((value) => <option key={value} value={value}>{formatHour(value)}</option>)}
      </select>
      <span className="caption">{config.timezone}</span>
      <button type="button" className="diagnosis-toggle" aria-pressed={Boolean(diagnosis)}
        aria-describedby="diagnosis-range-note" onClick={() => dispatch({ type: 'toggleDiagnosis' })}>
        <span aria-hidden="true">{diagnosis ? '✓' : '◎'}</span> Diagnosis
      </button>
    </div>
    <p id="diagnosis-range-note" className="caption diagnosis-range-note" role="status">
      {diagnosis ? 'Diagnosis is on. All service dates are locked; turn Diagnosis off to change the range.'
        : 'Diagnosis is off. Choose any date range, or enable Diagnosis to use all service dates.'}
    </p>
    <DateRangeSlider dateRange={dateRange} max={config.service_dates.length - 1} dates={config.service_dates}
      disabled={Boolean(diagnosis)}
      onChange={(value) => dispatch({ type: 'setDateRange', dateRange: value })} />
    {error && <p className="error-banner" role="alert">{error}</p>}
    <div className="metric-grid" aria-busy={!summary && !error}>
      <Metric label="Observed readings" value={summary ? `${summary.n} / ${summary.planned}` : '—'} />
      <Metric label="Center line" value={decimal(summary?.cl)} />
      <Metric label="LCL" value={decimal(limits?.lcl)} />
      <Metric label="UCL" value={decimal(limits?.ucl)} />
    </div>
    {data ? <HistoryChart key={settledKey} data={data} station={station} hour={hour}
      timezone={config.timezone} diagnosis={Boolean(diagnosis)} />
      : !error && <div className="chart history-chart pending"><p className="chart-message" role="status">Loading same-hour analysis…</p></div>}
    {summary && (!limits ? <p className="info-message" role="status">{summary.reason}</p>
      : <p className="caption">Estimated from {summary.pairs} consecutive service-date pairs at {formatHour(hour)} · mean moving range {limits.mr_mean.toFixed(3)} · sigma estimate {limits.sigma.toFixed(3)}.</p>)}
    <p className="caption analysis-note">Missing scheduled readings remain gaps and break moving-range pairs. These exploratory limits may reflect serial dependence; they do not establish process stability or trigger alarms.</p>
  </section>
}
