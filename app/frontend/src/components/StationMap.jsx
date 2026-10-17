import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import 'maplibre-gl/dist/maplibre-gl.css'
import { STATUS, count, formatTime } from '../format.js'
import './StationMap.css'

maplibregl.setWorkerUrl(workerUrl)

function mapStyle(tiles) {
  if (tiles) return 'https://tiles.openfreemap.org/styles/positron'
  return {
    version: 8,
    sources: {},
    layers: [
      { id: 'background', type: 'background', paint: { 'background-color': '#f0f4f0' } },
    ],
  }
}

function popupContent(station, timezone) {
  const container = document.createElement('div')
  container.className = 'station-popup'
  const title = document.createElement('strong')
  title.textContent = `${station.station_id} · ${station.display_name}`
  container.append(title)
  const amount = station.suggested_change ? ` ${Math.abs(station.suggested_change)}` : ''
  const lines = [
    `Current bikes: ${count(station.bikes)} / ${station.capacity}`,
    `Free docks: ${count(station.free_docks)}`,
    `Status: ${STATUS[station.status].label}`,
    `Action: ${station.action}${amount}`,
    `Latest reading: ${count(station.latest_bikes)} bikes · ${formatTime(station.latest_timestamp, timezone, true)}`,
    `Reading age: ${station.age_minutes === null ? 'Unknown' : `${count(station.age_minutes)} min`}`,
  ]
  lines.forEach((text) => {
    const line = document.createElement('div')
    line.textContent = text
    container.append(line)
  })
  return container
}

export default function StationMap({ stations, selected, tiles, timezone, onSelect, camera,
  highlightedStation = null, onHoverStation, onFocusStation }) {
  const container = useRef(null)
  const map = useRef(null)
  const markers = useRef(new Map())
  const displayedTiles = useRef(tiles)
  const onSelectRef = useRef(onSelect)
  const onHoverRef = useRef(onHoverStation)
  const onFocusRef = useRef(onFocusStation)
  const hoveredStation = useRef(null)
  const focusedStation = useRef(null)
  const availableStations = useRef(new Set())
  const [tileError, setTileError] = useState(false)
  onSelectRef.current = onSelect
  onHoverRef.current = onHoverStation
  onFocusRef.current = onFocusStation
  availableStations.current = new Set(stations.map((station) => station.station_id))

  function clearInteractions(stationId = null) {
    if (hoveredStation.current !== null && (stationId === null || hoveredStation.current === stationId)) {
      hoveredStation.current = null
      onHoverRef.current?.(null)
    }
    if (focusedStation.current !== null && (stationId === null || focusedStation.current === stationId)) {
      focusedStation.current = null
      onFocusRef.current?.(null)
    }
  }

  useEffect(() => {
    const instance = new maplibregl.Map({
      container: container.current, style: mapStyle(tiles),
      center: camera.current?.center || [-76.486, 42.4517],
      zoom: camera.current?.zoom ?? 12.2,
      attributionControl: { compact: true },
      dragRotate: false, pitchWithRotate: false,
    })
    map.current = instance
    displayedTiles.current = tiles
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    instance.on('error', () => setTileError(true))
    instance.on('style.load', () => setTileError(false))
    const observer = new ResizeObserver(() => instance.resize())
    observer.observe(container.current)
    return () => {
      camera.current = { center: instance.getCenter().toArray(), zoom: instance.getZoom() }
      observer.disconnect()
      markers.current.forEach(({ marker, popup, button }) => {
        button.classList.remove('linked-highlight')
        popup.remove()
        marker.remove()
      })
      clearInteractions()
      markers.current.clear()
      instance.remove()
      map.current = null
    }
  }, [])

  useEffect(() => {
    const instance = map.current
    if (displayedTiles.current !== tiles) {
      displayedTiles.current = tiles
      instance.setStyle(mapStyle(tiles))
      setTileError(false)
    }
  }, [tiles])

  useEffect(() => {
    const instance = map.current
    if (!stations.length) {
      markers.current.forEach(({ popup, button }) => {
        popup.remove()
        button.classList.remove('linked-highlight')
      })
      clearInteractions()
      return
    }
    const ids = new Set(stations.map((station) => station.station_id))
    markers.current.forEach((entry, id) => {
      if (!ids.has(id)) {
        entry.button.classList.remove('linked-highlight')
        entry.popup.remove()
        entry.marker.remove()
        markers.current.delete(id)
        clearInteractions(id)
      }
    })
    stations.forEach((station) => {
      let entry = markers.current.get(station.station_id)
      if (!entry) {
        const button = document.createElement('button')
        button.type = 'button'
        button.className = 'station-marker'
        button.dataset.station = station.station_id
        const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 17, maxWidth: '320px' })
        const marker = new maplibregl.Marker({ element: button })
          .setLngLat([station.longitude, station.latitude]).addTo(instance)
        button.addEventListener('mouseenter', () => {
          if (!availableStations.current.has(station.station_id)) return
          popup.addTo(instance)
          hoveredStation.current = station.station_id
          onHoverRef.current?.(station.station_id)
        })
        button.addEventListener('mouseleave', () => {
          if (focusedStation.current !== station.station_id) popup.remove()
          if (hoveredStation.current === station.station_id) {
            hoveredStation.current = null
            onHoverRef.current?.(null)
          }
        })
        button.addEventListener('focus', () => {
          if (!availableStations.current.has(station.station_id)) return
          popup.addTo(instance)
          focusedStation.current = station.station_id
          onFocusRef.current?.(station.station_id)
        })
        button.addEventListener('blur', () => {
          if (hoveredStation.current !== station.station_id) popup.remove()
          if (focusedStation.current === station.station_id) {
            focusedStation.current = null
            onFocusRef.current?.(null)
          }
        })
        button.addEventListener('click', (event) => event.stopPropagation())
        button.addEventListener('dblclick', (event) => {
          event.preventDefault()
          event.stopPropagation()
          onSelectRef.current(station.station_id)
        })
        button.addEventListener('keydown', (event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            event.stopPropagation()
            onSelectRef.current(station.station_id)
          }
        })
        entry = { marker, popup, button }
        markers.current.set(station.station_id, entry)
      }
      entry.button.style.setProperty('--marker-color', STATUS[station.status].color)
      entry.button.setAttribute('aria-label', `${station.station_id} · ${station.display_name}: ${STATUS[station.status].label}, ${count(station.bikes)} of ${station.capacity} bikes. Double-click or press Enter to select.`)
      entry.popup.setLngLat([station.longitude, station.latitude]).setDOMContent(popupContent(station, timezone))
    })
  }, [stations, timezone])

  useEffect(() => {
    markers.current.forEach(({ button }, id) => {
      button.classList.toggle('selected', id === selected)
      button.setAttribute('aria-pressed', String(id === selected))
    })
  }, [selected, stations])

  useEffect(() => {
    markers.current.forEach(({ button }, id) => {
      button.classList.toggle('linked-highlight', stations.length > 0 && id === highlightedStation)
    })
  }, [highlightedStation, stations])

  return <>
    <div ref={container} className="station-map" aria-label="Map of 20 simulated Ithaca bikeshare stations" />
    <div className="map-legend" aria-label="Station status legend">
      {Object.entries(STATUS).map(([key, value]) => <span key={key}><i style={{ background: value.color }} />{value.label}</span>)}
    </div>
    {!tiles && <p className="caption">Tile-free fallback: real station coordinates on a blank background.</p>}
    {tiles && tileError && <p className="caption">Street tiles could not load. Turn off Street basemap for a tile-free station view.</p>}
  </>
}
