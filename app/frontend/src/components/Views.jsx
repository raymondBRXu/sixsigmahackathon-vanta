import { useEffect, useState } from 'react'
import { apiUrl } from '../api.js'
import { useResource } from '../hooks.js'
import { count, decimal, formatDate, formatHour, formatTime, moveLabel, percent, STATUS } from '../format.js'
import { DateRangeSlider } from './Controls.jsx'
import StationMap from './StationMap.jsx'

export function Metric({ label, value, detail }) {
  return <div className="metric"><span className="metric-label">{label}</span><strong>{value}</strong>{detail && <span className="metric-detail">{detail}</span>}</div>
}

export function StatusBadge({ status }) {
  return <span className="status-badge" style={{ '--status-color': STATUS[status].color }}><i />{STATUS[status].label}</span>
}

function Chart({ kind, params, alt }) {
  const url = apiUrl(`charts/${kind}.svg`, params)
  return <ChartImage key={url} url={url} alt={alt} kind={kind} />
}

function ChartImage({ url, alt, kind }) {
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState(false)
  return <div className={`chart ${kind === 'history' ? 'history-chart' : ''} ${loaded ? 'loaded' : 'pending'}`}>
    {!loaded && !error && <p className="chart-message" role="status">Drawing chart…</p>}
    {error ? <p className="chart-message error" role="alert">This chart could not load. Change the selection or reload to try again.</p>
      : <img src={url} alt={alt} onLoad={() => setLoaded(true)} onError={() => setError(true)} />}
  </div>
}

export function Operations({ state, dispatch, camera }) {
  const { source, cursor, station, config, tiles } = state
  const { data, error } = useResource('snapshot', { source, cursor })
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
        <h2>Ithaca — simulated bikeshare network</h2>
        <p className="caption">Hover for a reading and action. Double-click a station to select its details.</p>
        <div className="map-shell">
          <StationMap stations={data?.stations || []} selected={station} tiles={tiles}
            timezone={config.timezone} camera={camera}
            onSelect={(id) => dispatch({ type: 'selectStation', station: id })} />
          {!data && !error && <div className="map-loading" role="status">Loading snapshot…</div>}
        </div>
      </div>
      <div className="queue-panel">
        <h2>Action queue</h2>
        <p className="caption">Empty / full first, then low / high stock. Proposed moves target 50% occupancy.</p>
        {data && (data.queue.length ? <div className="queue-scroll">
          <table className="queue-table">
            <caption className="sr-only">Current station inventory actions</caption>
            <thead><tr><th>Station</th><th>Bikes</th><th>State</th><th>Move</th></tr></thead>
            <tbody>{data.queue.map((row) => <tr key={row.station_id}>
              <td><strong>{row.station_id}</strong><span className="queue-station-name">{row.display_name}</span></td>
              <td>{count(row.bikes)}</td><td><StatusBadge status={row.status} /></td><td className="move">{moveLabel(row.suggested_change)}</td>
            </tr>)}</tbody>
          </table>
        </div> : <div className="success-message"><span aria-hidden="true">✓</span> No current inventory threshold actions.</div>)}
        {!data && !error && <div className="queue-placeholder" aria-hidden="true" />}
        <p className="caption queue-note">Amounts are station targets, not a balanced truck route. Verify readings before a physical move.</p>
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
  const { source, historyStation: station, dateRange, hour, config } = state
  const cursor = config.timestamps.length - 1
  const params = { source, cursor, station_id: station, hour,
    start_date: config.service_dates[dateRange[0]], end_date: config.service_dates[dateRange[1]] }
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
      <p className="caption">Compare this station at the same operating hour across service dates. Each point is one observed bike count. The full dataset is available; choose the dates to plot below.</p>
    </div>
    <div className="hour-selector">
      <label htmlFor="analysis-hour">Operating hour</label>
      <select id="analysis-hour" value={hour} onChange={(event) => dispatch({ type: 'selectHour', hour: Number(event.target.value) })}>
        {config.hours.map((value) => <option key={value} value={value}>{formatHour(value)}</option>)}
      </select>
      <span className="caption">{config.timezone}</span>
    </div>
    <DateRangeSlider dateRange={dateRange} max={config.service_dates.length - 1} dates={config.service_dates}
      onChange={(value) => dispatch({ type: 'setDateRange', dateRange: value })} />
    {error && <p className="error-banner" role="alert">{error}</p>}
    <div className="metric-grid" aria-busy={!summary && !error}>
      <Metric label="Observed readings" value={summary ? `${summary.n} / ${summary.planned}` : '—'} />
      <Metric label="Center line" value={decimal(summary?.cl)} />
      <Metric label="LCL" value={decimal(limits?.lcl)} />
      <Metric label="UCL" value={decimal(limits?.ucl)} />
    </div>
    {data ? <Chart kind="history" params={settledParams} alt={`Individuals chart for ${station} at ${formatHour(hour)} on each service date from ${formatDate(params.start_date)} through ${formatDate(params.end_date)}, with dates on the horizontal axis, center line and estimated control limits when supported.`} />
      : !error && <div className="chart history-chart pending"><p className="chart-message" role="status">Loading same-hour analysis…</p></div>}
    {summary && (!limits ? <p className="info-message" role="status">{summary.reason}</p>
      : <p className="caption">Estimated from {summary.pairs} consecutive service-date pairs at {formatHour(hour)} · mean moving range {limits.mr_mean.toFixed(3)} · sigma estimate {limits.sigma.toFixed(3)}.</p>)}
    <p className="caption analysis-note">Missing scheduled readings remain gaps and break moving-range pairs. These exploratory limits may reflect serial dependence; they do not establish process stability or trigger alarms.</p>
  </section>
}
