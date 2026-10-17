export const initialState = {
  config: null,
  source: 'normal',
  cursor: 0,
  dateRange: [0, 0],
  hour: 7,
  station: 'S01',
  operationsView: 'Overview',
  historyStation: null,
  diagnosis: false,
  playing: false,
  tiles: true,
  loading: true,
  error: '',
}

function moveCursor(state, cursor) {
  const next = Math.max(0, Math.min(cursor, state.config.timestamps.length - 1))
  return {
    ...state,
    cursor: next,
  }
}

export function dashboardReducer(state, action) {
  switch (action.type) {
    case 'sourceRequested':
      return { ...state, source: action.source, loading: true, playing: false, historyStation: null, diagnosis: false, error: '' }
    case 'sourceLoaded': {
      const config = action.config
      const cursor = config.default_cursor
      const station = config.stations.some((item) => item.station_id === state.station)
        ? state.station : config.stations[0].station_id
      const hour = config.hours.includes(state.hour) ? state.hour : config.hours[0]
      return { ...state, config, source: config.source.id, station, cursor, hour,
        dateRange: [0, config.service_dates.length - 1], historyStation: null, diagnosis: false, playing: false, loading: false, error: '' }
    }
    case 'sourceFailed':
      return { ...state, loading: false, error: action.message, playing: false }
    case 'selectStation':
      return { ...state, station: action.station, playing: false }
    case 'selectHour':
      return state.config.hours.includes(action.hour) ? { ...state, hour: action.hour } : state
    case 'selectOperationsView':
      return { ...state, operationsView: action.view, historyStation: null, diagnosis: false }
    case 'openHistory':
      if (!state.config?.stations.some((station) => station.station_id === action.station)) return state
      return { ...state, historyStation: action.station, playing: false, diagnosis: false,
        hour: state.config.hours.includes(7) ? 7 : state.config.hours[0],
        dateRange: [0, state.config.service_dates.length - 1] }
    case 'closeHistory':
      return { ...state, historyStation: null, diagnosis: false }
    case 'toggleDiagnosis':
      if (!state.historyStation || !state.config) return state
      return { ...state, diagnosis: !state.diagnosis,
        dateRange: [0, state.config.service_dates.length - 1] }
    case 'setTiles':
      return { ...state, tiles: action.tiles }
    case 'setCursor':
      return { ...moveCursor(state, action.cursor), playing: false }
    case 'step':
      return { ...moveCursor(state, state.cursor + action.direction), playing: false }
    case 'setDateRange': {
      if (state.diagnosis) return state
      const maxDate = state.config.service_dates.length - 1
      const start = Math.max(0, Math.min(action.dateRange[0], maxDate))
      const end = Math.max(start, Math.min(action.dateRange[1], maxDate))
      return { ...state, dateRange: [start, end] }
    }
    case 'togglePlayback':
      return { ...state, playing: !state.historyStation && !state.loading
        && state.cursor < state.config.timestamps.length - 1 && !state.playing }
    case 'tick': {
      if (!state.playing || state.historyStation) return state
      const next = moveCursor(state, state.cursor + 1)
      return { ...next, playing: next.cursor < state.config.timestamps.length - 1 }
    }
    default:
      return state
  }
}
