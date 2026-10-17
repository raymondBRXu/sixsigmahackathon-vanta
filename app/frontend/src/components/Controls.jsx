import { formatTime } from '../format.js'

export function Clock({ state, dispatch }) {
  const { config, cursor, playing, view } = state
  const time = (index) => formatTime(config.timestamps[index], config.timezone)
  return <section className="clock" aria-label="Simulation playback">
    <div className="clock-heading">
      <strong>{formatTime(config.timestamps[cursor], config.timezone, true)}</strong>
      <span className="clock-tag">SIMULATION TIME</span>
    </div>
    <div className="playback-buttons">
      <button className="primary" onClick={() => dispatch({ type: 'togglePlayback' })}
        disabled={view === 'Analysis' || (cursor === config.timestamps.length - 1 && !playing)}>
        <span aria-hidden="true">{playing ? 'Ⅱ' : '▶'}</span> {playing ? 'Pause' : 'Play'}
      </button>
      <button onClick={() => dispatch({ type: 'step', direction: -1 })} disabled={cursor === 0}>← Step</button>
      <button onClick={() => dispatch({ type: 'step', direction: 1 })} disabled={cursor === config.timestamps.length - 1}>Step →</button>
    </div>
    {view === 'Analysis' && <p className="caption playback-note">Playback paused for analysis; scrub or step to change the shared time.</p>}
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

export function IntervalSlider({ interval, max, timestamps, timezone, onChange }) {
  const [start, end] = interval
  const percent = (index) => index / Math.max(max, 1) * 100
  const time = (index) => formatTime(timestamps[index], timezone)
  return <fieldset className="interval-selector">
    <legend>Analysis time range</legend>
    <div className="interval-labels"><span><small>FROM</small>{time(start)}</span><span><small>THROUGH</small>{time(end)}</span></div>
    <div className="dual-range" style={{ '--start': `${percent(start)}%`, '--end': `${percent(end)}%` }}>
      <div className="range-track" />
      <input type="range" min="0" max={max} step="1" value={start}
        aria-label="Analysis start" aria-valuetext={time(start)}
        style={{ zIndex: start === max ? 4 : 2 }}
        onChange={(event) => onChange([Math.min(Number(event.target.value), end), end])} />
      <input type="range" min="0" max={max} step="1" value={end}
        aria-label="Analysis end" aria-valuetext={time(end)}
        onChange={(event) => onChange([start, Math.max(Number(event.target.value), start)])} />
    </div>
    <div className="interval-fields">
      <label>Start reading<select aria-label="Analysis start reading" value={start}
        onChange={(event) => onChange([Number(event.target.value), end])}>
        {timestamps.slice(0, end + 1).map((stamp, index) => <option key={stamp} value={index}>{time(index)}</option>)}
      </select></label>
      <label>End reading<select aria-label="Analysis end reading" value={end}
        onChange={(event) => onChange([start, Number(event.target.value)])}>
        {timestamps.slice(start, max + 1).map((stamp, offset) => <option key={stamp} value={start + offset}>{time(start + offset)}</option>)}
      </select></label>
    </div>
  </fieldset>
}
