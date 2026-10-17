import { formatDate, formatTime } from '../format.js'

export function Clock({ state, dispatch }) {
  const { config, cursor, playing, historyStation } = state
  const time = (index) => formatTime(config.timestamps[index], config.timezone)
  return <section className="clock" aria-label="Simulation playback">
    <div className="clock-heading">
      <strong>{formatTime(config.timestamps[cursor], config.timezone, true)}</strong>
      <span className="clock-tag">SIMULATION TIME</span>
    </div>
    <div className="playback-buttons">
      <button className="primary" onClick={() => dispatch({ type: 'togglePlayback' })}
        disabled={Boolean(historyStation) || (cursor === config.timestamps.length - 1 && !playing)}>
        <span aria-hidden="true">{playing ? 'Ⅱ' : '▶'}</span> {playing ? 'Pause' : 'Play'}
      </button>
      <button onClick={() => dispatch({ type: 'step', direction: -1 })} disabled={cursor === 0}>← Step</button>
      <button onClick={() => dispatch({ type: 'step', direction: 1 })} disabled={cursor === config.timestamps.length - 1}>Step →</button>
    </div>
    <div className="clock-slider">
      <div className="slider-current">{time(cursor)}</div>
      <input type="range" min="0" max={config.timestamps.length - 1} step="1" value={cursor}
        aria-label="Simulation time" aria-valuetext={time(cursor)}
        style={{ '--progress': `${cursor / Math.max(1, config.timestamps.length - 1) * 100}%` }}
        onChange={(event) => dispatch({ type: 'setCursor', cursor: Number(event.target.value) })} />
      <div className="slider-extents"><span>{time(0)}</span><span>{time(config.timestamps.length - 1)}</span></div>
    </div>
  </section>
}

export function DateRangeSlider({ dateRange, max, dates, onChange, disabled = false }) {
  const [start, end] = dateRange
  const percent = (index) => index / Math.max(max, 1) * 100
  const date = (index) => formatDate(dates[index])
  return <fieldset className="interval-selector" disabled={disabled}>
    <legend>Analysis date range</legend>
    <div className="interval-labels"><span><small>FROM</small>{date(start)}</span><span><small>THROUGH</small>{date(end)}</span></div>
    <div className="dual-range" style={{ '--start': `${percent(start)}%`, '--end': `${percent(end)}%` }}>
      <div className="range-track" />
      <input type="range" min="0" max={max} step="1" value={start}
        aria-label="Analysis start date" aria-valuetext={date(start)} disabled={disabled || max === 0}
        style={{ zIndex: start === max ? 4 : 2 }}
        onChange={(event) => onChange([Math.min(Number(event.target.value), end), end])} />
      <input type="range" min="0" max={max} step="1" value={end}
        aria-label="Analysis end date" aria-valuetext={date(end)} disabled={disabled || max === 0}
        onChange={(event) => onChange([start, Math.max(Number(event.target.value), start)])} />
    </div>
    <div className="interval-fields">
      <label>Start date<select value={start} disabled={disabled}
        onChange={(event) => onChange([Number(event.target.value), end])}>
        {dates.slice(0, end + 1).map((day, index) => <option key={day} value={index}>{date(index)}</option>)}
      </select></label>
      <label>End date<select value={end} disabled={disabled}
        onChange={(event) => onChange([start, Number(event.target.value)])}>
        {dates.slice(start, max + 1).map((day, offset) => <option key={day} value={start + offset}>{date(start + offset)}</option>)}
      </select></label>
    </div>
  </fieldset>
}
