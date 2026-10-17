export const initialState = {
  config: null,
  source: 'normal',
  cursor: 0,
  interval: [0, 0],
  station: 'S01',
  view: 'Operations',
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
    interval: state.interval.map((value) => Math.min(value, next)),
  }
}

export function dashboardReducer(state, action) {
  switch (action.type) {
    case 'sourceRequested':
      return { ...state, source: action.source, loading: true, playing: false, error: '' }
    case 'sourceLoaded': {
      const config = action.config
      const cursor = config.default_cursor
      const station = config.stations.some((item) => item.station_id === state.station)
        ? state.station : config.stations[0].station_id
      return { ...state, config, source: config.source.id, station, cursor,
        interval: [0, cursor], playing: false, loading: false, error: '' }
    }
    case 'sourceFailed':
      return { ...state, loading: false, error: action.message, playing: false }
    case 'selectStation':
      return { ...state, station: action.station, playing: false }
    case 'selectView':
      return { ...state, view: action.view, playing: false }
    case 'setTiles':
      return { ...state, tiles: action.tiles }
    case 'setCursor':
      return { ...moveCursor(state, action.cursor), playing: false }
    case 'step':
      return { ...moveCursor(state, state.cursor + action.direction), playing: false }
    case 'setInterval': {
      const start = Math.max(0, Math.min(action.interval[0], state.cursor))
      const end = Math.max(start, Math.min(action.interval[1], state.cursor))
      return { ...state, interval: [start, end] }
    }
    case 'togglePlayback':
      return { ...state, playing: state.view === 'Operations' && !state.loading
        && state.cursor < state.config.timestamps.length - 1 && !state.playing }
    case 'tick': {
      if (!state.playing || state.view !== 'Operations') return state
      const next = moveCursor(state, state.cursor + 1)
      return { ...next, playing: next.cursor < state.config.timestamps.length - 1 }
    }
    default:
      return state
  }
}
