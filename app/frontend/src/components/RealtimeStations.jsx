import { useEffect, useId, useRef, useState } from 'react'
import { formatTime } from '../format.js'
import { useResource } from '../hooks.js'
import './RealtimeStations.css'

const WINDOW_SIZE = 8
const REFERENCE_LINES = { center: 15, upper: 24, lower: 6 }
const PLOT = { left: 26, right: 292, top: 16, bottom: 130 }
const xPosition = (slot) => PLOT.left + slot * (PLOT.right - PLOT.left) / (WINDOW_SIZE - 1)
const yPosition = (bikes) => PLOT.bottom - bikes * (PLOT.bottom - PLOT.top) / 30

function chartSlots(timestamps, timezone) {
  const hours = new Intl.DateTimeFormat('en-GB', { timeZone: timezone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
  const days = new Intl.DateTimeFormat('en-CA', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit' })
  const recent = timestamps.slice(-WINDOW_SIZE)
  return recent.map((timestamp, index) => ({
    timestamp,
    slot: WINDOW_SIZE - recent.length + index,
    hour: hours.format(new Date(timestamp)),
    day: days.format(new Date(timestamp)),
    time: formatTime(timestamp, timezone),
    fullTime: formatTime(timestamp, timezone, true),
    epoch: new Date(timestamp).getTime(),
  }))
}

function StationCard({ station, readings, slots, referenceLines, timestamp, timezone, loading, error, expanded, onExpand, expandRef, onHistory }) {
  const id = useId()
  const history = new Map(readings?.history.map((reading) => [reading.timestamp, reading.bikes]) || [])
  const series = slots.map((slot) => ({ ...slot, bikes: history.get(slot.timestamp) ?? null }))
  const latest = history.get(timestamp)
  const latestLabel = loading ? 'Updating…' : error ? 'Unavailable' : latest == null ? 'No reading' : `${latest} / ${station.capacity} bikes`
  const segments = series.flatMap((point, index) => {
    const previous = series[index - 1]
    if (point.bikes === null || !previous || previous.bikes === null
      || point.epoch - previous.epoch !== 3600000 || point.day !== previous.day) return []
    return [`M${xPosition(previous.slot)},${yPosition(previous.bikes)} L${xPosition(point.slot)},${yPosition(point.bikes)}`]
  })

  return <article className={`realtime-station-card ${expanded ? 'realtime-station-expanded' : 'realtime-station-clickable'}`}
    aria-labelledby={`${id}-heading`} onClick={expanded ? undefined : onExpand}>
    <header className="realtime-station-heading">
      <span className="realtime-station-id">{station.station_id}</span>
      <h3 id={`${id}-heading`} title={`${station.station_id} · ${station.display_name}`}>{station.display_name}</h3>
      <button className="realtime-history" type="button"
        aria-label={`History for ${station.station_id} · ${station.display_name}`}
        onClick={(event) => {
          event.stopPropagation()
          event.currentTarget.focus()
          onHistory(station.station_id)
        }}>History</button>
    </header>
    <div className="realtime-latest" aria-label={`Latest scheduled reading for ${station.station_id}`}>
      <strong>{latestLabel}</strong>
      <time dateTime={timestamp} title={timestamp ? formatTime(timestamp, timezone, true) : undefined}>{timestamp ? formatTime(timestamp, timezone) : 'Awaiting time'}</time>
    </div>
    <svg className="realtime-chart" width="306" height="171" viewBox="0 0 306 171" role="img"
      ref={expanded ? undefined : expandRef} tabIndex={expanded ? undefined : 0}
      aria-description={expanded ? undefined : 'Press Enter or Space to enlarge this chart.'}
      onKeyDown={expanded ? undefined : (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onExpand()
        }
      }}
      aria-labelledby={`${id}-chart-title`} aria-describedby={`${id}-chart-description`}>
      <title id={`${id}-chart-title`}>{station.station_id} · {station.display_name}: last eight scheduled bike readings</title>
      <desc id={`${id}-chart-description`}>Fixed scale: 0 to 30 bikes, eight hourly slots. Fixed inventory reference lines: CL {referenceLines.center}, Upper {referenceLines.upper}, Lower {referenceLines.lower}. Missing readings and overnight gaps are not connected.</desc>
      {[0, 30].map((value) => <g key={value} className="realtime-axis">
        <line x1={PLOT.left} x2={PLOT.right} y1={yPosition(value)} y2={yPosition(value)} />
        <text x={PLOT.left - 7} y={yPosition(value) + 4} textAnchor="end">{value}</text>
      </g>)}
      {[
        ['upper', 'Upper', referenceLines.upper],
        ['center', 'CL', referenceLines.center],
        ['lower', 'Lower', referenceLines.lower],
      ].map(([key, label, value]) => <g key={key} className={`realtime-reference realtime-reference-${key}`}>
        <line x1={PLOT.left} x2={PLOT.right} y1={yPosition(value)} y2={yPosition(value)} />
        <text x={PLOT.right} y={yPosition(value) - 4} textAnchor="end">{label} {value}</text>
      </g>)}
      <g className="realtime-x-axis">
        {Array.from({ length: WINDOW_SIZE }, (_, slot) => {
          const reading = slots.find((item) => item.slot === slot)
          return <g key={slot}>
            <line x1={xPosition(slot)} x2={xPosition(slot)} y1={PLOT.bottom} y2={PLOT.bottom + 4} />
            <text x={xPosition(slot)} y="149" textAnchor="middle">
              {reading && <title>{reading.time} · {timezone}</title>}
              {reading?.hour || '—'}
            </text>
          </g>
        })}
      </g>
      <path className="realtime-trace" d={segments.join(' ')} />
      {series.filter((point) => point.bikes !== null).map((point) => <circle key={point.timestamp}
        className={`realtime-point${point.bikes < referenceLines.lower || point.bikes > referenceLines.upper ? ' outside-reference' : ''}`}
        cx={xPosition(point.slot)} cy={yPosition(point.bikes)} r="3.5" data-timestamp={point.timestamp} data-bikes={point.bikes}>
        <title>{station.station_id} · {station.display_name} · {point.fullTime} ({point.timestamp}) · {point.bikes} bikes</title>
      </circle>)}
      {series.filter((point) => point.bikes === null).map((point) => <text key={point.timestamp}
        className="realtime-missing" x={xPosition(point.slot)} y="163" textAnchor="middle">
        <title>{station.station_id} · {point.time}: missing scheduled reading</title>×
      </text>)}
    </svg>
  </article>
}

export default function RealtimeStations({ state, onHistory }) {
  const { source, cursor, config, playing } = state
  const [expandedStation, setExpandedStation] = useState(null)
  const backButton = useRef(null)
  const expandButtons = useRef(new Map())
  const returnStation = useRef(null)
  const { data, error } = useResource('realtime', { source, cursor })
  const timezone = config.timezone
  const referenceLines = data?.reference_lines || REFERENCE_LINES
  const slots = chartSlots(data?.timestamps || [], timezone)
  const timestamp = data?.timestamp || config.timestamps[cursor]
  const readingsByStation = new Map(data?.stations.map((station) => [station.station_id, station]) || [])
  const visibleStations = expandedStation
    ? config.stations.filter((station) => station.station_id === expandedStation)
    : config.stations

  useEffect(() => {
    if (expandedStation) {
      backButton.current?.focus()
      const onKeyDown = (event) => {
        if (event.key === 'Escape' && !event.defaultPrevented && !event.target.closest('dialog')) {
          event.preventDefault()
          setExpandedStation(null)
        }
      }
      window.addEventListener('keydown', onKeyDown)
      return () => window.removeEventListener('keydown', onKeyDown)
    }
    if (returnStation.current) {
      expandButtons.current.get(returnStation.current)?.focus()
      returnStation.current = null
    }
  }, [expandedStation])

  return <section className="realtime-view" aria-label="View by Station" aria-busy={!data && !error}>
    <div className="realtime-heading">
      <h2>View by Station</h2>
      <span className={`realtime-playback-status${playing ? ' playing' : ''}`}><i aria-hidden="true" />{playing ? 'Playing simulation' : 'Simulation paused'}</span>
    </div>
    <p className="caption realtime-caption">Synthetic simulation playback · {timezone}. Each station shows the latest eight scheduled hourly slots. Fixed inventory reference lines: CL {referenceLines.center}, Upper {referenceLines.upper}, Lower {referenceLines.lower} bikes.</p>
    <div className="realtime-request-status">
      {error ? <p role="alert">Station readings could not load: {error}</p>
        : !data ? <p role="status">Updating station readings…</p>
          : <p>Shared scale: 0–30 bikes · Hover points and hours for dates · × missing reading</p>}
    </div>
    {expandedStation
      ? <div className="realtime-focus-toolbar">
        <button ref={backButton} type="button" onClick={() => setExpandedStation(null)}>← Back to all stations</button>
        <span className="caption">Esc to return</span>
      </div>
      : <p className="caption realtime-expand-hint">Click a chart to enlarge it, or choose History to compare dates.</p>}
    <div className={expandedStation ? 'realtime-single-view' : 'realtime-grid-scroll'}>
      <div className={expandedStation ? 'realtime-single-chart' : 'realtime-station-grid'}>
        {visibleStations.map((station) => <StationCard key={station.station_id} station={station}
          readings={readingsByStation.get(station.station_id)} slots={slots} referenceLines={referenceLines}
          timestamp={timestamp} timezone={timezone} loading={!data && !error} error={error}
          expanded={Boolean(expandedStation)} onHistory={onHistory}
          expandRef={(button) => {
            if (button) expandButtons.current.set(station.station_id, button)
            else expandButtons.current.delete(station.station_id)
          }}
          onExpand={() => {
            returnStation.current = station.station_id
            setExpandedStation(station.station_id)
          }} />)}
      </div>
    </div>
  </section>
}
