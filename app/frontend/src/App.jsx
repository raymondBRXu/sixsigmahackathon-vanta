import { useCallback, useEffect, useReducer, useRef } from 'react'
import { requestJson } from './api.js'
import { dashboardReducer, initialState } from './state.js'
import { Clock } from './components/Controls.jsx'
import { Operations } from './components/Views.jsx'
import RealtimeStations from './components/RealtimeStations.jsx'
import HistoryDialog from './components/HistoryDialog.jsx'
import { useResource } from './hooks.js'
import useInventoryAlerts from './useInventoryAlerts.js'

export default function App() {
  const [state, dispatch] = useReducer(dashboardReducer, initialState)
  const sourceRequest = useRef(null)
  const camera = useRef(null)
  const uploadInput = useRef(null)
  const { config, loading, error } = state
  const snapshot = useResource('snapshot', { source: state.source, cursor: state.cursor }, Boolean(config && !loading && !error))
  const inventoryAlerts = useInventoryAlerts(state.source, state.cursor, snapshot.data)

  const loadSource = useCallback(async (source, file) => {
    sourceRequest.current?.abort()
    const controller = new AbortController()
    sourceRequest.current = controller
    dispatch({ type: 'sourceRequested', source })
    const body = file ? new FormData() : undefined
    if (file) body.append('file', file)
    try {
      const next = await requestJson(file ? 'uploads' : 'config', {
        signal: controller.signal, body, method: file ? 'POST' : 'GET',
        params: file ? undefined : { source },
      })
      if (!controller.signal.aborted) dispatch({ type: 'sourceLoaded', config: next })
    } catch (failure) {
      if (!controller.signal.aborted) dispatch({ type: 'sourceFailed', message: failure.message })
    }
  }, [])

  useEffect(() => {
    loadSource('normal')
    return () => sourceRequest.current?.abort()
  }, [loadSource])

  useEffect(() => {
    if (!state.playing) return undefined
    const timer = setInterval(() => dispatch({ type: 'tick' }), 2000)
    return () => clearInterval(timer)
  }, [state.playing])

  const scenarios = config?.scenarios || [{ id: 'normal', label: 'Normal operations' }, { id: 'disruption', label: 'Disruption' }]
  const customSource = !scenarios.some((item) => item.id === state.source)
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to dashboard</a>
    <aside className="sidebar" aria-label="Dashboard settings">
      <a className="brand" href="#main-content"><span className="brand-mark" aria-hidden="true">◉</span> DockWatch</a>
      <p className="brand-subtitle">TEAM VANTA / ITHACA, NY</p>
      <div className="sidebar-divider" />
      <label className="field-label" htmlFor="scenario">Demo scenario</label>
      <select id="scenario" value={state.source} onChange={(event) => {
        if (uploadInput.current) uploadInput.current.value = ''
        loadSource(event.target.value)
      }}>
        {scenarios.map((scenario) => <option key={scenario.id} value={scenario.id}>{scenario.label}</option>)}
        {customSource && <option value={state.source}>{state.source === 'uploading' ? error ? 'CSV could not load' : 'Loading CSV…' : config?.source.label || 'Uploaded CSV'}</option>}
      </select>
      <details className="upload-panel">
        <summary>Use your own observations</summary>
        <label className="field-label" htmlFor="upload">Upload inventory CSV</label>
        <input id="upload" ref={uploadInput} type="file" accept=".csv,text/csv"
          onChange={(event) => {
            const file = event.target.files[0]
            if (file) loadSource('uploading', file)
          }} />
        <p className="caption">timestamp · station_id · bikes. Uses the supplied station list and hourly calendar.</p>
      </details>
      <label className="field-label" htmlFor="station">Station</label>
      <select id="station" value={state.station} disabled={!config || loading}
        onChange={(event) => dispatch({ type: 'selectStation', station: event.target.value })}>
        {config?.stations.map((station) => <option key={station.station_id} value={station.station_id}>{station.station_id} · {station.display_name}</option>)}
      </select>
      {config && !loading && !error && <Clock state={state} dispatch={dispatch} />}
      <label className="toggle-control"><input type="checkbox" checked={state.tiles}
        onChange={(event) => dispatch({ type: 'setTiles', tiles: event.target.checked })} /><span className="toggle-track" aria-hidden="true" /><span>Street basemap</span></label>
      <p className="caption toggle-help">Turn off for a tile-free view when offline.</p>
      <div className="sidebar-divider" />
      <div className="simulation-note">
        <strong>Simulation, clearly labeled.</strong>
        <p>20 fictional stations · 300 bikes</p>
        <p>Hourly readings, 07:00–21:00</p>
        <p>America/New_York</p>
        {config && !loading && !error && <p className="source-info">Source: {config.source.label}<br />{config.source.observations.toLocaleString()} observations</p>}
      </div>
      <details className="definitions">
        <summary>What the numbers mean</summary>
        <p><strong>Two-way availability:</strong> a current reading has both a bike and an empty dock.</p>
        <p><strong>Coverage:</strong> valid current readings / planned stations.</p>
        <p><strong>Inventory rule:</strong> below 20% or above 80% suggests moving toward half capacity.</p>
        <p><strong>Individuals chart:</strong> compares one station at the same operating hour across selected service dates, with its mean and estimated control limits; interpretation is left to you.</p>
      </details>
      <div className="sidebar-footer"><span className="tiny-dot" /> SYNTHETIC OBSERVATIONS</div>
    </aside>
    <main id="main-content">
      <header className="page-header">
        <div><p className="eyebrow">BIKESHARE OPERATIONS / SIX SIGMA HACKATHON</p><h1>A clearer view of every dock.</h1><p className="lede">Spot service gaps. Understand the pattern. Prioritize the next move.</p></div>
        <div className="demo-label"><span>● SYNTHETIC DEMO</span><small>Ithaca · Team Vanta</small></div>
      </header>
      {loading ? <div className="loading-panel" role="status"><span className="loading-dot" />Loading observations…</div>
        : error ? <div className="error-banner" role="alert"><strong>The observation file could not be loaded.</strong><p>{error}</p><p>Correct the file and upload it again, or select a demo scenario.</p><button onClick={() => loadSource('normal')}>Use normal operations</button></div>
          : config && <>
            <nav className="operations-tabs" aria-label="Dashboard views">
              {['Overview', 'View by Station'].map((view) => <button key={view}
                aria-pressed={state.operationsView === view} className={state.operationsView === view ? 'active' : ''}
                onClick={() => dispatch({ type: 'selectOperationsView', view })}>{view}</button>)}
            </nav>
            {state.operationsView === 'View by Station' ? <RealtimeStations state={state}
              initialExpandedStation={state.realtimeStation}
              onHistory={(station) => dispatch({ type: 'openHistory', station })} />
              : <Operations state={state} dispatch={dispatch} camera={camera} snapshot={snapshot} inventoryAlerts={inventoryAlerts} />}
            {state.historyStation && <HistoryDialog state={state} dispatch={dispatch} />}
          </>}
      <footer className="page-footer">DOCKWATCH / TEAM VANTA · Synthetic inventory observations. No customer-attempt, exact outage-duration or causal performance claims.</footer>
    </main>
  </div>
}
