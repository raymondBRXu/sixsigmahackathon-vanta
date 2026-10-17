import { useId, useRef, useState } from 'react'
import { decimal, formatHour } from '../format.js'
import './HistoryChart.css'

const PLOT = { width: 960, height: 390, left: 64, right: 875, top: 34, bottom: 322 }
const isNumber = (value) => typeof value === 'number' && Number.isFinite(value)

function dateLabel(timestamp, timezone, full = false) {
  return new Intl.DateTimeFormat('en-US', {
    timeZone: timezone, month: 'short', day: '2-digit', ...(full ? { year: 'numeric' } : {}),
  }).format(new Date(timestamp))
}

export default function HistoryChart({ data, station, hour, timezone = 'America/New_York', diagnosis = false }) {
  const id = useId()
  const history = data.history || []
  const summary = data.summary || {}
  const limits = summary.limits
  const specialCauses = summary.special_causes
  const issues = diagnosis ? specialCauses?.issues || [] : []
  const [selectedRule, setSelectedRule] = useState(issues[0]?.id)
  const [hoveredIndex, setHoveredIndex] = useState(null)
  const [focusedIndex, setFocusedIndex] = useState(null)
  const [pinnedIndex, setPinnedIndex] = useState(null)
  const tabRefs = useRef(new Map())
  const selectedIssue = issues.find((issue) => issue.id === selectedRule) || issues[0]
  const validIndices = new Set(history.flatMap((point, index) => isNumber(point.bikes) ? [index] : []))
  const selectedIndices = new Set((selectedIssue?.point_indices || []).filter((index) => validIndices.has(index)))
  const pointRules = new Map()
  issues.forEach((issue) => {
    new Set(issue.point_indices).forEach((index) => {
      if (validIndices.has(index)) pointRules.set(index, [...(pointRules.get(index) || []), issue.id])
    })
  })

  const values = [0, isNumber(data.capacity) ? data.capacity : 30, summary.cl, limits?.lcl, limits?.ucl,
    ...history.map((point) => point.bikes)].filter(isNumber)
  const low = Math.min(...values)
  const high = Math.max(...values)
  const padding = Math.max((high - low) * 0.09, 1)
  const min = low - padding
  const max = high + padding
  const x = (index) => history.length < 2 ? (PLOT.left + PLOT.right) / 2
    : PLOT.left + index * (PLOT.right - PLOT.left) / (history.length - 1)
  const y = (value) => PLOT.bottom - (value - min) * (PLOT.bottom - PLOT.top) / (max - min)
  const segments = history.flatMap((point, index) => {
    const previous = history[index - 1]
    return isNumber(point.bikes) && previous && isNumber(previous.bikes)
      ? [`M${x(index - 1)},${y(previous.bikes)} L${x(index)},${y(point.bikes)}`] : []
  })
  const tickStep = Math.max(1, Math.ceil(history.length / 8))
  const dateTicks = history.map((point, index) => ({ ...point, index }))
    .filter(({ index }) => index % tickStep === 0 || index === history.length - 1)
  const yTicks = Array.from({ length: 5 }, (_, index) => low + (high - low) * index / 4)
  const activeIndex = hoveredIndex ?? focusedIndex ?? pinnedIndex
  const activePoint = activeIndex === null ? null : history[activeIndex]
  const activeRules = pointRules.get(activeIndex) || []
  const ruleStatuses = diagnosis ? Object.entries(specialCauses?.rule_status || {}) : []
  const unavailable = ruleStatuses.filter(([, result]) => result.status === 'unavailable')
  const hasEvaluatedRules = ruleStatuses.some(([, result]) => result.evaluated_windows > 0 && result.status !== 'unavailable')
  const panelId = `${id}-panel`
  const tooltipId = `${id}-point-information`
  const chartName = `Individuals chart for ${station} at ${formatHour(hour)} across service dates`
  const patternLabel = (rules) => rules.length ? `Patterns: ${rules.join(', ')}`
    : hasEvaluatedRules ? 'No detected pattern for this point' : 'Pattern tests unavailable'

  function selectTab(event, index) {
    const keys = { ArrowLeft: (index - 1 + issues.length) % issues.length,
      ArrowRight: (index + 1) % issues.length, Home: 0, End: issues.length - 1 }
    if (!(event.key in keys)) return
    event.preventDefault()
    const next = issues[keys[event.key]]
    setSelectedRule(next.id)
    tabRefs.current.get(next.id)?.focus()
  }

  return <div className="interactive-history">
    <div id={panelId} role={issues.length ? 'tabpanel' : undefined}
      aria-labelledby={selectedIssue ? `${id}-tab-${selectedIssue.id}` : undefined}>
      {diagnosis && <div className={`history-diagnosis-summary${selectedIssue ? ' detected' : ''}`} aria-live="polite">
        {selectedIssue ? <>
          <h3>{selectedIssue.id} · {selectedIssue.title}</h3>
          <p>{selectedIssue.description}</p>
          <p className="history-diagnosis-count">{selectedIndices.size} unique {selectedIndices.size === 1 ? 'point' : 'points'} highlighted in red · {selectedIssue.event_count} {selectedIssue.event_count === 1 ? 'match' : 'matches'}. Other detected patterns are outlined in amber.</p>
        </> : <p>{hasEvaluatedRules
          ? 'No unusual patterns detected in the evaluated tests.'
          : 'Diagnosis unavailable for this selection.'}</p>}
      </div>}

      <div className="history-plot-scroll" tabIndex={0} aria-label="Scrollable history chart">
        <svg className="history-interactive-chart" viewBox={`0 0 ${PLOT.width} ${PLOT.height}`}
          role="group" aria-roledescription="interactive chart" aria-labelledby={`${id}-chart-title`}
          aria-describedby={`${id}-chart-description`} data-y-min={min} data-y-max={max}>
          <title id={`${id}-chart-title`}>{chartName}</title>
          <desc id={`${id}-chart-description`}>One observed bike count per selected service date. Hover, focus or tap a point for its date, hour and value. Missing readings remain gaps. The center line and estimated control limits are shown when available.</desc>
          {yTicks.map((value, index) => <g className="history-y-tick" key={index}>
            <line x1={PLOT.left} x2={PLOT.right} y1={y(value)} y2={y(value)} />
            <text x={PLOT.left - 12} y={y(value) + 5} textAnchor="end">{Number(value.toFixed(1))}</text>
          </g>)}
          <text className="history-axis-label" x={PLOT.left} y="17">Bikes</text>
          {diagnosis && isNumber(summary.cl) && isNumber(limits?.sigma) && limits.sigma > 0
            && [-2, -1, 1, 2].map((multiple) => <g key={multiple} className="history-sigma-guide">
              <line x1={PLOT.left} x2={PLOT.right} y1={y(summary.cl + multiple * limits.sigma)} y2={y(summary.cl + multiple * limits.sigma)} />
              <text x={PLOT.right + 9} y={y(summary.cl + multiple * limits.sigma) + 4}>{multiple > 0 ? '+' : '−'}{Math.abs(multiple)}σ</text>
            </g>)}
          {[
            ['ucl', 'UCL', limits?.ucl], ['cl', 'CL', summary.cl], ['lcl', 'LCL', limits?.lcl],
          ].filter(([, , value]) => isNumber(value)).map(([key, label, value]) => <g key={key} className={`history-control-line history-control-${key}`} data-value={value}>
            <line x1={PLOT.left} x2={PLOT.right} y1={y(value)} y2={y(value)} />
            <text x={PLOT.right + 9} y={y(value) + 5}>{label} {decimal(value)}</text>
          </g>)}
          <path className="history-series-line" d={segments.join(' ')} />
          {history.map((point, index) => {
            if (!isNumber(point.bikes)) return <g key={point.timestamp} className="history-missing" data-index={index}>
              <text x={x(index)} y={PLOT.bottom + 4} textAnchor="middle">×</text>
              <title>{dateLabel(point.timestamp, timezone, true)} · {formatHour(hour)}: missing scheduled reading</title>
            </g>
            const rules = pointRules.get(index) || []
            const selected = diagnosis && selectedIndices.has(index)
            const flagged = rules.length > 0
            const label = `${dateLabel(point.timestamp, timezone, true)} · ${formatHour(hour)} · ${point.bikes} bikes${diagnosis ? ` · ${patternLabel(rules)}` : ''}`
            return <g key={point.timestamp} className={`history-point${flagged ? ' history-point-flagged' : ''}${selected ? ' history-point-selected' : ''}${activeIndex === index ? ' history-point-active' : ''}`}
              role="button" tabIndex={0} aria-label={label} aria-describedby={activeIndex === index ? tooltipId : undefined}
              aria-pressed={pinnedIndex === index} data-index={index} data-bikes={point.bikes} data-rules={rules.join(' ')}
              onMouseEnter={() => setHoveredIndex(index)} onMouseLeave={() => setHoveredIndex(null)}
              onFocus={() => setFocusedIndex(index)} onBlur={() => setFocusedIndex(null)}
              onClick={() => setPinnedIndex(pinnedIndex === index ? null : index)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  setPinnedIndex(pinnedIndex === index ? null : index)
                }
              }}>
              <circle className="history-point-hit" cx={x(index)} cy={y(point.bikes)} r="11" />
              {flagged && <circle className="history-point-ring" cx={x(index)} cy={y(point.bikes)} r="7" />}
              <circle className="history-point-dot" cx={x(index)} cy={y(point.bikes)} r="4.5" />
            </g>
          })}
          <g className="history-date-axis">
            <line x1={PLOT.left} x2={PLOT.right} y1={PLOT.bottom} y2={PLOT.bottom} />
            {dateTicks.map((point) => <g key={point.timestamp}>
              <line x1={x(point.index)} x2={x(point.index)} y1={PLOT.bottom} y2={PLOT.bottom + 5} />
              <text x={x(point.index)} y={PLOT.bottom + 25} textAnchor="middle">{dateLabel(point.timestamp, timezone)}</text>
            </g>)}
          </g>
          <text className="history-axis-label" x={(PLOT.left + PLOT.right) / 2} y="379" textAnchor="middle">Service date · {formatHour(hour)} · {timezone}</text>
        </svg>
      </div>

      <div className={`history-point-information${activePoint ? ' active' : ''}`}>
        {activePoint ? <div role="tooltip" id={tooltipId}>
          <strong>{dateLabel(activePoint.timestamp, timezone, true)} · {formatHour(hour)}</strong>
          <span>{activePoint.bikes} bikes · {station} · {timezone}</span>
          {diagnosis && <span>{patternLabel(activeRules)}</span>}
        </div> : <p>Hover, focus or tap a point to inspect its date, hour and bike count. × marks a missing reading.</p>}
      </div>
    </div>

    {diagnosis && issues.length > 0 && <div className="history-issue-tabs" role="tablist" aria-label="Detected patterns">
      {issues.map((issue, index) => <button key={issue.id} type="button" role="tab"
        id={`${id}-tab-${issue.id}`} aria-controls={panelId} aria-selected={selectedIssue.id === issue.id}
        tabIndex={selectedIssue.id === issue.id ? 0 : -1}
        ref={(element) => { if (element) tabRefs.current.set(issue.id, element); else tabRefs.current.delete(issue.id) }}
        onClick={() => setSelectedRule(issue.id)} onKeyDown={(event) => selectTab(event, index)}>
        <span>{issue.id}</span>{issue.title}
      </button>)}
    </div>}
    {diagnosis && unavailable.length > 0 && <details className="history-unavailable-rules">
      <summary>{unavailable.length} {unavailable.length === 1 ? 'test unavailable' : 'tests unavailable'}</summary>
      <ul>{unavailable.map(([rule, result]) => <li key={rule}><strong>{rule}:</strong> {result.reason || 'Insufficient data to evaluate this test.'}</li>)}</ul>
    </details>}
  </div>
}
