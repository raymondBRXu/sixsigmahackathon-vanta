import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import HistoryChart from './HistoryChart.jsx'

afterEach(cleanup)

const readings = [0, 14, 28, 15, null, 18, 27, 26, 16, 15]
const history = readings.map((bikes, index) => ({ timestamp: `2026-09-${String(index + 1).padStart(2, '0')}T07:00:00-04:00`, bikes }))
const issues = [
  { id: 'T1', title: 'Beyond three sigma', description: 'One reading lies strictly outside the three-sigma limits.', point_indices: [2, 6], event_count: 2 },
  { id: 'T2', title: 'Two of three beyond two sigma', description: 'Two of three consecutive readings exceed two sigma on the same side.', point_indices: [6, 7, 6], event_count: 2 },
  { id: 'T3', title: 'Four of five beyond one sigma', description: 'Four of five consecutive readings exceed one sigma on the same side.', point_indices: [1, 2], event_count: 1 },
]
const ruleStatus = Object.fromEntries(issues.map((issue) => [issue.id, { status: 'detected', reason: null, evaluated_windows: 4 }]))
const data = {
  capacity: 30, history,
  summary: {
    cl: 15, limits: { lcl: -3, ucl: 33, sigma: 6 },
    special_causes: {
      status: 'enabled', issues, rule_status: ruleStatus,
      events: [{ rule: 'T2', start_index: 5, end_index: 7, trigger_index: 7, contributing_indices: [6, 7] }],
    },
  },
}
const props = { data, station: 'S01', hour: 7, timezone: 'America/New_York' }
const pointIndices = (container, selector) => [...container.querySelectorAll(selector)].map((point) => Number(point.getAttribute('data-index')))

describe('interactive History chart', () => {
  it('reveals every valid reading by hover, focus and persistent tap, including zero', () => {
    render(<HistoryChart {...props} />)
    const chart = screen.getByRole('group', { name: /^Individuals chart for S01 at 07:00/ })
    const points = within(chart).getAllByRole('button')
    expect(points).toHaveLength(9)
    expect(points.every((point) => point.getAttribute('tabindex') === '0')).toBe(true)
    const zero = within(chart).getByRole('button', { name: 'Sep 01, 2026 · 07:00 · 0 bikes' })
    fireEvent.mouseEnter(zero)
    expect(screen.getByRole('tooltip').textContent).toContain('Sep 01, 2026 · 07:00')
    expect(screen.getByRole('tooltip').textContent).toContain('0 bikes · S01')
    fireEvent.mouseLeave(zero)
    expect(screen.queryByRole('tooltip')).toBeNull()
    fireEvent.focus(points[2])
    expect(screen.getByRole('tooltip').textContent).toContain('28 bikes')
    expect(points[2].getAttribute('aria-describedby')).toBe(screen.getByRole('tooltip').id)
    fireEvent.blur(points[2])
    fireEvent.click(zero)
    expect(zero.getAttribute('aria-pressed')).toBe('true')
    fireEvent.mouseLeave(zero)
    expect(screen.getByRole('tooltip').textContent).toContain('0 bikes')
    fireEvent.keyDown(zero, { key: ' ' })
    expect(zero.getAttribute('aria-pressed')).toBe('false')
    expect(screen.queryByRole('tooltip')).toBeNull()
    expect(screen.queryByRole('tablist')).toBeNull()
  })

  it('flags the union of contributing points and selects all unique points of the first detected rule', () => {
    const { container } = render(<HistoryChart {...props} diagnosis />)
    expect(pointIndices(container, '.history-point-flagged')).toEqual([1, 2, 6, 7])
    expect(pointIndices(container, '.history-point-selected')).toEqual([2, 6])
    expect(container.querySelector('[data-index="5"]').getAttribute('data-rules')).toBe('')
    expect(screen.getByText('2 unique points highlighted in red · 2 matches. Other detected patterns are outlined in amber.')).toBeTruthy()
    expect(screen.getByText(issues[0].description)).toBeTruthy()
    const tabs = screen.getAllByRole('tab')
    expect(tabs).toHaveLength(3)
    expect(tabs[0].getAttribute('aria-selected')).toBe('true')
    expect(tabs[0].getAttribute('aria-controls')).toBe(screen.getByRole('tabpanel').id)
    expect(screen.getByRole('tabpanel').getAttribute('aria-labelledby')).toBe(tabs[0].id)
    expect(container.querySelector('.history-plot-scroll').contains(screen.getByRole('tablist'))).toBe(false)
    expect(screen.getByRole('tabpanel').compareDocumentPosition(screen.getByRole('tablist')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('shows overlapping rule IDs in the tooltip and changes red points without coloring whole detection windows', () => {
    const { container } = render(<HistoryChart {...props} diagnosis />)
    const overlap = container.querySelector('.history-point[data-index="6"]')
    fireEvent.mouseEnter(overlap)
    expect(screen.getByRole('tooltip').textContent).toContain('Patterns: T1, T2')
    fireEvent.click(screen.getByRole('tab', { name: /T2 Two of three/ }))
    expect(pointIndices(container, '.history-point-selected')).toEqual([6, 7])
    expect(pointIndices(container, '.history-point-flagged')).toEqual([1, 2, 6, 7])
    expect(container.querySelector('.history-point[data-index="5"]').classList.contains('history-point-flagged')).toBe(false)
    expect(screen.getByText(issues[1].description)).toBeTruthy()
    expect(screen.queryByText(issues[0].description)).toBeNull()
    expect(screen.getByText(/2 unique points highlighted/)).toBeTruthy()
  })

  it('supports arrow, Home and End keys with roving tab focus and a matching panel', () => {
    render(<HistoryChart {...props} diagnosis />)
    const tabs = screen.getAllByRole('tab')
    fireEvent.keyDown(tabs[0], { key: 'ArrowRight' })
    expect(document.activeElement).toBe(tabs[1])
    expect(tabs[1].getAttribute('aria-selected')).toBe('true')
    expect(tabs[0].tabIndex).toBe(-1)
    expect(tabs[1].tabIndex).toBe(0)
    expect(screen.getByRole('tabpanel').getAttribute('aria-labelledby')).toBe(tabs[1].id)
    fireEvent.keyDown(tabs[1], { key: 'End' })
    expect(document.activeElement).toBe(tabs[2])
    fireEvent.keyDown(tabs[2], { key: 'ArrowRight' })
    expect(document.activeElement).toBe(tabs[0])
    fireEvent.keyDown(tabs[0], { key: 'ArrowLeft' })
    expect(document.activeElement).toBe(tabs[2])
    fireEvent.keyDown(tabs[2], { key: 'Home' })
    expect(document.activeElement).toBe(tabs[0])
  })

  it('preserves missing slots and breaks the trace instead of connecting across a missing observation', () => {
    const { container } = render(<HistoryChart {...props} />)
    expect(container.querySelectorAll('.history-missing')).toHaveLength(1)
    expect(container.querySelector('.history-missing').getAttribute('data-index')).toBe('4')
    const path = container.querySelector('.history-series-line').getAttribute('d')
    expect(path.match(/L/g)).toHaveLength(7)
    const missingX = Number(container.querySelector('.history-missing text').getAttribute('x'))
    expect(path).not.toContain(`L${missingX},`)
    expect(container.querySelector('.history-point[data-index="0"]').getAttribute('data-bikes')).toBe('0')
    expect(container.innerHTML).not.toMatch(/NaN|Infinity/)
  })

  it('includes negative and above-capacity control limits and shows sigma guides only during diagnosis', () => {
    const { container, rerender } = render(<HistoryChart {...props} />)
    const chart = screen.getByRole('group', { name: /^Individuals chart/ })
    expect(Number(chart.getAttribute('data-y-min'))).toBeLessThan(-3)
    expect(Number(chart.getAttribute('data-y-max'))).toBeGreaterThan(33)
    expect(container.querySelector('.history-control-lcl').getAttribute('data-value')).toBe('-3')
    expect(container.querySelector('.history-control-ucl').getAttribute('data-value')).toBe('33')
    expect(screen.getByText('LCL -3.00')).toBeTruthy()
    expect(screen.getByText('UCL 33.00')).toBeTruthy()
    expect(container.querySelectorAll('.history-sigma-guide')).toHaveLength(0)
    rerender(<HistoryChart {...props} diagnosis />)
    expect(container.querySelectorAll('.history-sigma-guide')).toHaveLength(4)
  })

  it('distinguishes no detected patterns from unavailable tests and explains partial availability', () => {
    const results = { status: 'enabled', issues: [], events: [], rule_status: {
      T1: { status: 'not_detected', reason: null, evaluated_windows: 10 },
      T6: { status: 'unavailable', reason: 'At least 15 consecutive valid readings are required.', evaluated_windows: 0 },
    } }
    const { rerender } = render(<HistoryChart {...props} diagnosis data={{ ...data, summary: { ...data.summary, special_causes: results } }} />)
    expect(screen.getByText('No unusual patterns detected in the evaluated tests.')).toBeTruthy()
    expect(screen.getByText('1 test unavailable')).toBeTruthy()
    fireEvent.click(screen.getByText('1 test unavailable'))
    expect(screen.getByText('At least 15 consecutive valid readings are required.')).toBeTruthy()
    expect(screen.queryByRole('tablist')).toBeNull()
    results.rule_status.T1 = { status: 'unavailable', reason: 'The sigma estimate is unavailable.', evaluated_windows: 0 }
    rerender(<HistoryChart {...props} diagnosis data={{ ...data, summary: { ...data.summary, special_causes: results } }} />)
    expect(screen.getByText('Diagnosis unavailable for this selection.')).toBeTruthy()
    expect(screen.queryByText(/No unusual patterns detected/)).toBeNull()
    expect(screen.getByText('2 tests unavailable')).toBeTruthy()
    fireEvent.focus(screen.getAllByRole('button')[0])
    expect(screen.getByRole('tooltip').textContent).toContain('Pattern tests unavailable')
  })

  it.each([
    { name: 'empty', history: [], cl: null },
    { name: 'all missing', history: history.map((point) => ({ ...point, bikes: null })), cl: null },
    { name: 'one zero', history: history.slice(0, 1), cl: 0 },
    { name: 'constant', history: history.map((point) => ({ ...point, bikes: 15 })), cl: 15 },
  ])('renders $name data without invalid geometry or invented limits', ({ history, cl }) => {
    const { container } = render(<HistoryChart {...props} data={{ capacity: 30, history, summary: { cl, limits: null } }} />)
    expect(container.innerHTML).not.toMatch(/NaN|Infinity/)
    expect(container.querySelector('.history-control-lcl')).toBeNull()
    expect(container.querySelector('.history-control-ucl')).toBeNull()
    expect(container.querySelectorAll('.history-point')).toHaveLength(history.filter((point) => point.bikes !== null).length)
  })

  it('keeps the chart interactive while diagnosis is off without showing flags or issue data', () => {
    const { container } = render(<HistoryChart {...props} diagnosis={false} />)
    expect(container.querySelectorAll('.history-point-flagged, .history-point-selected')).toHaveLength(0)
    expect(container.querySelectorAll('.history-diagnosis-summary, .history-unavailable-rules')).toHaveLength(0)
    expect(screen.queryByRole('tablist')).toBeNull()
    fireEvent.focus(screen.getAllByRole('button')[2])
    expect(screen.getByRole('tooltip').textContent).toContain('28 bikes')
    expect(screen.getByRole('tooltip').textContent).not.toContain('Patterns:')
  })
})
