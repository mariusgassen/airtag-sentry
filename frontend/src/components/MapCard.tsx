import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import L from 'leaflet'
import { DomEvent } from 'leaflet'
import 'leaflet.heat'
import {
  Circle,
  CircleMarker,
  MapContainer,
  TileLayer,
  Polyline,
  Marker,
  Popup,
  Tooltip,
  useMap,
  useMapEvent,
} from 'react-leaflet'
import type { Airtag, OwnerLocation, Place, Report, ReportStay } from '../api'
import { getAddress } from '../api'
import {
  capitalize,
  formatAirtagBattery,
  formatClusterRange,
  formatDeviceBattery,
  formatRelative,
  isLowBattery,
} from '../format'
import { useAnimatedLatLng } from '../hooks/useAnimatedLatLng'
import { useCurrentPosition } from '../hooks/useCurrentPosition'
import {
  OWNER_TRAIL_COLOR,
  PIN_POPUP_OFFSET,
  PLACE_CIRCLE_COLOR,
  SIZE,
  airtagPinIcon,
  currentLocationIcon,
  deviceColor,
  hasOwnerTrails,
  recentOwnerTrailPoints,
  stayMarkerRadius,
} from '../mapIcons'
import { centerMarkerOnClick, mapsUrl } from '../maps'
import { CARTO_API_KEY } from '../mapTiles'
import { useColorScheme } from '../theme'
import { BatteryIcon, ClockIcon, LocationArrowIcon, MapPinIcon, PlusIcon, RouteIcon } from './icons'

/** Callback for "Ort hier hinzufügen" (see AddPlaceButton) - jumps to
 * Settings -> Orte and opens the place editor pre-seeded at this exact
 * position, so a geofence can be created from a location already on the
 * map instead of re-finding it by panning/searching from scratch. Optional
 * everywhere it's threaded through (App.tsx always supplies it in
 * practice) so this file's popups still render standalone in isolation
 * (e.g. Storybook-less manual testing). */
export type AddPlaceHandler = (lat: number, lon: number, name?: string) => void

// Every marker popup in the app (this file, DeviceMapCard.tsx, OverviewMap.tsx)
// shares this shape - a fixed width so the card doesn't reflow oddly between
// a short ("Letzte Position" only) and a long (address + prev/next) variant.
export const POPUP_WIDTH_CLASS = 'w-60'

// CARTO's Voyager/Dark Matter basemaps - same OSM data, styled by theme, but
// now require a free API key (see mapTiles.ts) or anonymous requests get a
// watermarked tile back. Falls back to plain, unstyled OSM tiles (no key
// needed) until one is configured in Settings -> Darstellung.
const PLAIN_OSM_TILE_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
const PLAIN_OSM_ATTRIBUTION = '&copy; OpenStreetMap contributors'
const LIGHT_TILE_URL = 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png'
const LIGHT_ATTRIBUTION = '&copy; OpenStreetMap contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
const DARK_TILE_URL = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
const DARK_ATTRIBUTION = '&copy; OpenStreetMap contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'

/** Tile layer for every map view in the app - swaps to CARTO's dark basemap
 * when the app is in dark mode (theme.ts's data-theme), so the map matches
 * the rest of the UI at night; light mode keeps the original OSM tiles
 * unchanged. Exported for DeviceMapCard.tsx/OverviewMap.tsx, which share
 * this same tile choice. */
export function AppTileLayer() {
  const scheme = useColorScheme()
  if (!CARTO_API_KEY) {
    return <TileLayer attribution={PLAIN_OSM_ATTRIBUTION} url={PLAIN_OSM_TILE_URL} />
  }
  return scheme === 'dark' ? (
    <TileLayer attribution={DARK_ATTRIBUTION} url={`${DARK_TILE_URL}?api_key=${CARTO_API_KEY}`} />
  ) : (
    <TileLayer attribution={LIGHT_ATTRIBUTION} url={`${LIGHT_TILE_URL}?api_key=${CARTO_API_KEY}`} />
  )
}

/** One icon-prefixed line of secondary popup info (timestamp, address, relative
 * time) - shared so every popup's metadata reads the same way. */
export function InfoRow({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <div className="mb-1 flex items-start gap-1.5 text-xs text-[var(--text-secondary)] last:mb-0">
      <span className="mt-0.5 shrink-0">{icon}</span>
      <span>{children}</span>
    </div>
  )
}

/** Fires onMapClick when the map background itself is tapped - Leaflet
 * markers stop click propagation, so this never fires for a marker/popup
 * tap. Used to let "click away from a pin" back out of a detail view (see
 * App.tsx's onMapClick). Exported for DeviceMapCard.tsx, which shares this
 * same behavior. */
export function MapClickHandler({ onMapClick }: { onMapClick?: () => void }) {
  useMapEvent('click', () => onMapClick?.())
  return null
}

export function FitBounds({ positions }: { positions: [number, number][] }) {
  const map = useMap()
  useEffect(() => {
    if (positions.length > 0) {
      // animate: false - PanToSelection (a sibling, run right after on the
      // same data change) always follows this with its own animated pan.
      // Leaflet's Map.setView _stop()s any in-progress animation before
      // starting a new one, and reads the *current* zoom to do it - so an
      // animated fitBounds here, still mid-flight toward its target zoom
      // when PanToSelection's panTo interrupts it a moment later, gets its
      // zoom change silently discarded (the map settles at the zoom it
      // started from, not the one fitBounds computed) even though its pan
      // committed instantly and its center looked briefly correct. Applying
      // this one instantly means there's nothing left to interrupt.
      map.fitBounds(positions, { padding: [24, 24], animate: false })
    }
  }, [map, positions])
  return null
}

/**
 * Leaflet caches its container size and only recalculates on window
 * `resize`. This two-pane layout resizes the map's container via CSS alone
 * (sidebar toggling, breakpoint changes) without the window itself
 * resizing, which otherwise leaves the map rendering into a stale-size box
 * (grey bands / misaligned tiles) - watch the container directly instead.
 */
export function InvalidateSizeOnResize() {
  const map = useMap()
  useEffect(() => {
    const container = map.getContainer()
    const observer = new ResizeObserver(() => map.invalidateSize())
    observer.observe(container)
    return () => observer.disconnect()
  }, [map])
  return null
}

const EXPAND_SVG =
  '<svg viewBox="0 0 24 24" width="16" height="16" fill="none"><path d="M9 4H4v5M15 4h5v5M4 15v5h5M20 15v5h-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
const COMPRESS_SVG =
  '<svg viewBox="0 0 24 24" width="16" height="16" fill="none"><path d="M4 9h5V4M20 9h-5V4M4 15h5v5M20 15h-5v5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'

/** Creates a bare `leaflet-bar` control button, wired to a single click
 * handler - the DOM scaffolding FullscreenControl and LocateControl each
 * need, since react-leaflet has no control primitive of its own (custom
 * controls are plain imperative Leaflet, same as EditableCircle.tsx's
 * imperative Circle). */
function controlButton(label: string, onClick: (e: Event) => void): HTMLAnchorElement {
  const button = L.DomUtil.create('a') as HTMLAnchorElement
  button.href = '#'
  button.setAttribute('role', 'button')
  button.setAttribute('aria-label', label)
  button.title = label
  button.style.cssText = 'display:flex;align-items:center;justify-content:center;color:#333'
  L.DomEvent.on(button, 'click', (e) => {
    L.DomEvent.preventDefault(e)
    onClick(e)
  })
  return button
}

function addControlButton(map: L.Map, button: HTMLAnchorElement): L.Control {
  const control = new L.Control({ position: 'topright' })
  control.onAdd = () => {
    const wrapper = L.DomUtil.create('div', 'leaflet-bar leaflet-control')
    wrapper.appendChild(button)
    L.DomEvent.disableClickPropagation(wrapper)
    return wrapper
  }
  control.addTo(map)
  return control
}

/** Toggles the map container in/out of the browser's Fullscreen API - handy
 * on mobile, where the map card sits cramped next to detail panels. Just the
 * browser's own Fullscreen API behind a Leaflet control, no plugin needed.
 * Renders nothing (and never enters fullscreen) when the browser doesn't
 * support it (`document.fullscreenEnabled` false - some embedded/older
 * WebViews). Exported for DeviceMapCard.tsx/OverviewMap.tsx, which share
 * this same control. */
export function FullscreenControl() {
  const map = useMap()
  useEffect(() => {
    if (!document.fullscreenEnabled) return
    const container = map.getContainer()
    const button = controlButton('Vollbild', () => {
      if (document.fullscreenElement === container) document.exitFullscreen()
      else container.requestFullscreen().catch(() => {})
    })
    button.innerHTML = EXPAND_SVG
    function sync() {
      button.innerHTML = document.fullscreenElement === container ? COMPRESS_SVG : EXPAND_SVG
    }
    document.addEventListener('fullscreenchange', sync)
    const control = addControlButton(map, button)
    return () => {
      document.removeEventListener('fullscreenchange', sync)
      control.remove()
    }
  }, [map])
  return null
}

const LOCATE_SVG =
  '<svg viewBox="0 0 24 24" width="16" height="16" fill="none"><circle cx="12" cy="12" r="3" fill="currentColor"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>'

/** "Locate me" control - centers/zooms the map on the browser's current GPS
 * position via Leaflet's own built-in `map.locate()` (no plugin needed), and
 * drops the same "you are here" pin (currentLocationIcon) NoReportsView's
 * fallback view uses. Useful for comparing your own position to the tracked
 * AirTag/device. Exported for DeviceMapCard.tsx/OverviewMap.tsx, which share
 * this same control. */
export function LocateControl() {
  const map = useMap()
  const [here, setHere] = useState<[number, number] | null>(null)

  useEffect(() => {
    const button = controlButton('Meinen Standort finden', () =>
      map.locate({ setView: true, maxZoom: 16, enableHighAccuracy: false }),
    )
    button.innerHTML = LOCATE_SVG
    function onFound(e: L.LocationEvent) {
      setHere([e.latlng.lat, e.latlng.lng])
    }
    map.on('locationfound', onFound)
    const control = addControlButton(map, button)
    return () => {
      map.off('locationfound', onFound)
      control.remove()
    }
  }, [map])

  if (!here) return null
  return <Marker position={here} icon={currentLocationIcon} eventHandlers={{ click: centerMarkerOnClick }} />
}

/** Pans (without changing zoom) to whichever position is currently
 * highlighted on the map - the latest one by default, or an explicitly
 * selected report/history entry - separate from FitBounds, which only
 * reframes the whole trail's zoom when the report list itself changes, not
 * on every selection. Always centering here (not just for an explicit
 * selection) is what makes every "highlighted" pin - including just
 * landing on an AirTag/device's detail view - end up centered, not only
 * ones reached via the history list or title-bar stepper. Exported for
 * DeviceMapCard.tsx, which shares this same selection behavior. */
export function PanToSelection({ position }: { position: [number, number] | null }) {
  const map = useMap()
  const lat = position?.[0]
  const lon = position?.[1]
  useEffect(() => {
    if (lat !== undefined && lon !== undefined) map.panTo([lat, lon], { animate: true })
  }, [map, lat, lon])
  return null
}

// Reverse-geocode results, keyed by "lat,lon" - avoids re-fetching the same
// point's address every time it's re-selected within a session (the backend
// caches too, but this skips the round-trip entirely).
const addressCache = new Map<string, string | null>()

/** Best-effort address line for a marker popup - starts blank, fills in (or
 * silently stays empty) once the lookup resolves, never blocks the popup.
 * Exported for DeviceMapCard.tsx, which shares this same popup content. */
export function AddressLine({ lat, lon }: { lat: number; lon: number }) {
  const key = `${lat},${lon}`
  const [address, setAddress] = useState<string | null | undefined>(() => addressCache.get(key))

  useEffect(() => {
    if (addressCache.has(key)) {
      setAddress(addressCache.get(key))
      return
    }
    let cancelled = false
    setAddress(undefined)
    getAddress(lat, lon)
      .then((a) => {
        addressCache.set(key, a)
        if (!cancelled) setAddress(a)
      })
      .catch(() => {
        if (!cancelled) setAddress(null)
      })
    return () => {
      cancelled = true
    }
  }, [key, lat, lon])

  if (!address) return null
  return (
    <InfoRow icon={<MapPinIcon className="h-3.5 w-3.5" />}>
      <span>{address}</span>
    </InfoRow>
  )
}

/** Battery reading for a marker popup, same info AirtagDetail.tsx/
 * DeviceDetail.tsx's headers already show - the popup was the one place
 * left without it (tasks/roadmap.md #9). Renders nothing for `null` (no
 * reading yet). Which formatter/label applies is inferred from `level`'s
 * type: a string is an AirTag's qualitative full/medium/low/very_low, a
 * number is a device's 0.0-1.0 fraction. Exported for DeviceMapCard.tsx,
 * which shares this same popup content (see CLAUDE.md's AirTag/device
 * parity constraint). */
export function BatteryRow({
  level,
  status,
  reported = true,
}: {
  level: string | number | null
  status?: string | null
  reported?: boolean
}) {
  if (level == null) return null
  return (
    <InfoRow icon={<BatteryIcon className="h-3.5 w-3.5" />}>
      <span
        className={isLowBattery(level) ? 'text-[var(--destructive)]' : undefined}
        title={reported ? undefined : 'Kein frischer Batteriewert bei diesem Fix - letzter bekannter Stand übernommen'}
      >
        {typeof level === 'string' ? formatAirtagBattery(level) : formatDeviceBattery(level, status ?? null)}
        {!reported && '*'}
      </span>
    </InfoRow>
  )
}

/** "Save this spot as a geofence" popup action - shared by every marker
 * popup in the app (this file, DeviceMapCard.tsx, OverviewMap.tsx) so
 * creating a place from an already-known location is always one tap away,
 * not just reachable by re-finding the same spot in Settings -> Orte from
 * scratch. Renders nothing when `onAddPlace` isn't wired up. */
export function AddPlaceButton({
  lat,
  lon,
  name,
  onAddPlace,
}: {
  lat: number
  lon: number
  name?: string | null
  onAddPlace?: AddPlaceHandler
}) {
  if (!onAddPlace) return null
  return (
    <button
      type="button"
      onClick={() => onAddPlace(lat, lon, name ?? undefined)}
      className="inline-flex items-center gap-1 rounded-lg border border-[var(--accent)] px-2.5 py-1.5 text-xs font-medium text-[var(--accent)]"
    >
      <PlusIcon className="h-3.5 w-3.5" />
      Ort hier hinzufügen
    </button>
  )
}

/** Dots along a trail for every history point other than the one currently
 * displayed (which already has its own full pin/popup) - lets a point be
 * picked directly on the map, not just via the sidebar history list. A
 * white ring around each device-colored fill keeps them visible against
 * the same-colored trail line they sit on, rather than blending into it.
 * Exported for DeviceMapCard.tsx, which shares this same behavior (see
 * CLAUDE.md's AirTag/device parity constraint). */
export function HistoryPoints<T extends { lat: number; lon: number }>({
  points,
  displayedIndex,
  color,
  getKey,
  getRadius,
  onSelect,
}: {
  points: T[]
  displayedIndex: number
  color: string
  getKey: (point: T, index: number) => string | number
  getRadius?: (point: T) => number
  onSelect?: (point: T) => void
}) {
  return (
    <>
      {points.map((point, i) =>
        i === displayedIndex ? null : (
          <CircleMarker
            key={getKey(point, i)}
            center={[point.lat, point.lon]}
            radius={getRadius ? getRadius(point) : 6}
            pathOptions={{ color: '#fff', weight: 2, fillColor: color, fillOpacity: 0.9, opacity: 0.9 }}
            eventHandlers={
              onSelect
                ? {
                    // CircleMarker (unlike Marker) bubbles its click to the
                    // map by default - left unstopped, picking a point also
                    // fired MapClickHandler's onMapClick right after,
                    // reading it as "tapped away from a pin" and closing
                    // the whole detail view the click was meant to refine.
                    click: (e) => {
                      DomEvent.stopPropagation(e)
                      onSelect(point)
                    },
                  }
                : undefined
            }
          />
        ),
      )}
    </>
  )
}

const HEATMAP_ICON_SVG =
  '<svg viewBox="0 0 24 24" width="16" height="16" fill="none"><path d="M12 3c-1.5 3-4.5 5-4.5 8.5A4.5 4.5 0 0 0 12 16a4.5 4.5 0 0 0 4.5-4.5c0-1-.3-1.8-.8-2.6-.3 1.4-1.2 2.1-1.9 2.1.6-2-.3-4-1.8-6Z" fill="currentColor"/><path d="M12 16v5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>'

/** Toggle-able density heatmap of stay points (leaflet.heat), weighted by
 * how many reports/fixes make up each stay - shows "where does this thing
 * usually sit" at a glance, alongside (not instead of) the individual
 * HistoryPoints dots, which stay clickable for picking a specific stay. Off
 * by default (a Leaflet control button turns it on) so it doesn't visually
 * compete with the trail/dots on first load. Exported for DeviceMapCard.tsx,
 * which shares this same overlay (see CLAUDE.md's AirTag/device parity
 * constraint). */
export function HeatmapLayer<T extends { lat: number; lon: number; count: number }>({ points }: { points: T[] }) {
  const map = useMap()
  const [visible, setVisible] = useState(false)
  const buttonRef = useRef<HTMLAnchorElement | null>(null)

  useEffect(() => {
    const button = controlButton('Häufigkeitskarte', () => setVisible((v) => !v))
    button.innerHTML = HEATMAP_ICON_SVG
    buttonRef.current = button
    const control = addControlButton(map, button)
    return () => {
      buttonRef.current = null
      control.remove()
    }
  }, [map])

  useEffect(() => {
    if (buttonRef.current) buttonRef.current.style.background = visible ? 'var(--accent)' : ''
    if (!visible) return
    const layer = L.heatLayer(
      points.map((p) => [p.lat, p.lon, p.count]),
      { radius: 28, blur: 22, maxZoom: 17 },
    ).addTo(map)
    return () => {
      layer.remove()
    }
  }, [map, visible, points])

  return null
}

/** Read-only translucent geofence overlays - the editable version (drag to
 * move/resize) only exists in SettingsPlaces.tsx's editor. Exported for
 * DeviceMapCard.tsx, which shares this same rendering (see CLAUDE.md's
 * AirTag/device parity constraint). */
export function PlaceCircles({ places }: { places: { id: number; name: string; lat: number; lon: number; radius_meters: number }[] }) {
  return (
    <>
      {places.map((p) => (
        <Circle
          key={p.id}
          center={[p.lat, p.lon]}
          radius={p.radius_meters}
          pathOptions={{ color: PLACE_CIRCLE_COLOR, weight: 2, fillColor: PLACE_CIRCLE_COLOR, fillOpacity: 0.1 }}
        />
      ))}
    </>
  )
}

/** Background trail for every *other* tracked owner device - drawn behind an
 * AirTag's own map (MapCard) or the overview map (OverviewMap), not a
 * device's own detail view (DeviceMapCard already shows its full history via
 * HistoryPoints/DeviceHistoryList, with no window applied). Off by default
 * (OwnerTrailToggle) and capped to OWNER_TRAIL_WINDOW_MS - a device's whole
 * history drawn unprompted on a map meant for something else was unreadable.
 * Faded per-segment from the oldest point (faint) to the newest (near-solid,
 * leading into that device's own full marker) rather than one flat line, so
 * which way the trail runs is visible without needing to click through it.
 * Exported for OverviewMap.tsx, which shares this same rendering. */
export function OwnerTrails({
  histories,
  visible,
}: {
  histories: Record<string, OwnerLocation[]>
  visible: boolean
}) {
  if (!visible) return null
  return (
    <>
      {Object.entries(histories).flatMap(([deviceId, history]) => {
        const points = recentOwnerTrailPoints(history)
        if (points.length < 2) return []
        return points.slice(1).map((point, i) => {
          const prev = points[i]
          const age = (i + 1) / (points.length - 1)
          return (
            <Polyline
              key={`${deviceId}-${i}`}
              positions={[
                [prev.lat, prev.lon],
                [point.lat, point.lon],
              ]}
              pathOptions={{ color: OWNER_TRAIL_COLOR, weight: 3, dashArray: '6 6', opacity: 0.12 + age * 0.68 }}
            />
          )
        })
      })}
    </>
  )
}

/** Off-by-default switch for OwnerTrails - a background trail for devices
 * other than the one actually being looked at was previously always drawn,
 * unprompted and unbounded, on every map. Exported for OverviewMap.tsx,
 * which shares this same control. */
export function OwnerTrailToggle({ visible, onToggle }: { visible: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={`absolute right-2 top-2 z-[500] inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium shadow ${
        visible
          ? 'border-[var(--accent)] bg-[var(--accent)] text-white'
          : 'border-[var(--divider)] bg-[var(--surface)] text-[var(--text-secondary)]'
      }`}
    >
      <RouteIcon className="h-3.5 w-3.5" />
      Verlauf eigener Geräte
    </button>
  )
}

/** Marker + popup for the map's one "selected" pin - the AirTag/device's own
 * currently displayed position. Not a plain `<Marker><Popup>` pair: a bound
 * Popup only opens on click, and there's no reliable way to force it open
 * on mount instead (an imperative `openPopup()` call from a sibling effect
 * empirically doesn't reliably run after react-leaflet's own bind-to-marker
 * effect finishes) - so the Popup here is standalone, positioned directly
 * rather than nested in the Marker, and opens itself unconditionally on
 * mount (react-leaflet's default behavior for a Popup with no parent
 * layer). That standalone-ness has two costs this component works around:
 * a Marker's own click, or picking a different position entirely (a
 * HistoryPoints dot, the header's older/newer stepper, a history-list row),
 * only ever *moves* a closed popup - Leaflet doesn't reopen it just because
 * its position changed - so a popup the user dismissed (X button, tap
 * elsewhere) stayed closed no matter which position got selected next,
 * silently showing nothing for it; the effect below reopens it on every
 * position change (including the initial mount, redundantly with the
 * default-open behavior above - openOn on an already-open popup is a no-op)
 * and the Marker's click handler covers the one case that isn't a position
 * change, re-clicking the same already-displayed pin. And a standalone
 * Popup has no icon to read `popupAnchor` from, so it needs `offset` passed
 * explicitly (PIN_POPUP_OFFSET) or it renders low enough to cover the pin's
 * own badge. Exported for DeviceMapCard.tsx, which shares this same
 * selected-pin behavior (see CLAUDE.md's AirTag/device parity
 * constraint). */
export function SelectedPin({
  position,
  icon,
  label,
  children,
}: {
  position: [number, number]
  icon: L.DivIcon
  // Permanent on-map name (e.g. a matched geofence's name) - shown above the
  // pin without needing a click, unlike the rest of the popup content.
  label?: string | null
  children: ReactNode
}) {
  const map = useMap()
  const popupRef = useRef<L.Popup>(null)
  const [lat, lon] = position
  useEffect(() => {
    popupRef.current?.openOn(map)
  }, [map, lat, lon])
  return (
    <>
      <Marker
        position={position}
        icon={icon}
        eventHandlers={{
          click: (e) => {
            centerMarkerOnClick(e)
            popupRef.current?.openOn(map)
          },
        }}
      >
        {label && (
          <Tooltip permanent direction="top" offset={[0, -SIZE]} className="!border-none !bg-transparent !shadow-none !p-0">
            <span className="rounded-full bg-[var(--surface)] px-2 py-0.5 text-[0.7rem] font-medium text-[var(--text)] shadow">
              {label}
            </span>
          </Tooltip>
        )}
      </Marker>
      {/* autoPan off: centerMarkerOnClick above already centers this pin
          explicitly on click. */}
      <Popup ref={popupRef} position={position} offset={PIN_POPUP_OFFSET} autoPan={false}>
        {children}
      </Popup>
    </>
  )
}

export function NoReportsView({
  onMapClick,
  onAddPlace,
}: { onMapClick?: () => void; onAddPlace?: AddPlaceHandler } = {}) {
  const here = useCurrentPosition()

  if (!here) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-[var(--surface)] text-sm text-[var(--text-secondary)]">
        Keine Standortdaten vorhanden.
      </div>
    )
  }

  return (
    <MapContainer center={here} zoom={14} className="h-full w-full">
      <AppTileLayer />
      <Marker position={here} icon={currentLocationIcon} eventHandlers={{ click: centerMarkerOnClick }}>
        {/* autoPan off: centerMarkerOnClick above already centers this pin
            explicitly on click. Same info shape as every other pin's popup
            in the app (address via AddressLine, "In Karten öffnen") rather
            than the bare title this used to be - this is a real, if
            approximate, position (the browser's own geolocation), not just
            filler for an AirTag/device with nothing to show yet. */}
        <Popup autoPan={false}>
          <div className={POPUP_WIDTH_CLASS}>
            <p className="mb-2 text-[0.95rem] font-semibold">Aktueller Standort</p>
            <AddressLine lat={here[0]} lon={here[1]} />
            <div className="mt-2 flex flex-wrap gap-2">
              <a
                href={mapsUrl(here[0], here[1], 'Aktueller Standort')}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded-lg border border-[var(--accent)] px-2.5 py-1.5 text-xs font-medium text-[var(--accent)]"
              >
                <LocationArrowIcon className="h-3.5 w-3.5" />
                In Karten öffnen
              </a>
              <AddPlaceButton lat={here[0]} lon={here[1]} onAddPlace={onAddPlace} />
            </div>
          </div>
        </Popup>
      </Marker>
      <MapClickHandler onMapClick={onMapClick} />
      <InvalidateSizeOnResize />
      <FullscreenControl />
    </MapContainer>
  )
}

export function MapCard({
  reports,
  stays,
  airtag,
  places = [],
  ownerLocations = [],
  ownerLocationHistories = {},
  onSelectDevice,
  selectedReportId = null,
  onSelectReport,
  onMapClick,
  onAddPlace,
}: {
  reports: Report[]
  // Server-computed (see stays.py / GET /api/reports) - already deduped,
  // labeled (geofence/correction/POI/address priority), and time-ranged.
  stays: ReportStay[]
  airtag: Airtag
  places?: Place[]
  ownerLocations?: OwnerLocation[]
  ownerLocationHistories?: Record<string, OwnerLocation[]>
  onSelectDevice?: (id: string) => void
  selectedReportId?: number | null
  onSelectReport?: (id: number) => void
  onMapClick?: () => void
  onAddPlace?: AddPlaceHandler
}) {
  // Memoized: reports itself is a stable reference across pure-selection
  // re-renders (App.tsx only replaces it on an actual re-fetch), but
  // `.map()` always returns a fresh array - without this, FitBounds below
  // (keyed on this same array) re-fits the *whole* trail on every render,
  // overriding PanToSelection's explicit centering on every older/newer
  // step or history-list pick.
  const positions = useMemo<[number, number][]>(() => reports.map((r) => [r.lat, r.lon]), [reports])
  const selectedIndex = selectedReportId != null ? stays.findIndex((s) => s.anchor_id === selectedReportId) : -1
  const displayedIndex = selectedIndex >= 0 ? selectedIndex : stays.length - 1
  const displayed = stays[displayedIndex] as ReportStay | undefined
  // Memoized: identical lat/lon must keep the same array reference across
  // renders, since it's also the standalone Popup's `position` prop below -
  // react-leaflet fully unbinds/rebinds that popup whenever the reference
  // changes (see the Popup's own comment), so a fresh array every render
  // would reopen it constantly instead of only on a real position change.
  const displayedPosition = useMemo<[number, number]>(
    () => [displayed?.lat ?? 0, displayed?.lon ?? 0],
    [displayed?.lat, displayed?.lon],
  )
  const animatedPosition = useAnimatedLatLng(displayedPosition)
  const [showOwnerTrail, setShowOwnerTrail] = useState(false)

  if (positions.length === 0 || !displayed) {
    return <NoReportsView onMapClick={onMapClick} onAddPlace={onAddPlace} />
  }

  const last = positions[positions.length - 1]
  const trailColor = deviceColor(airtag)

  return (
    <div className="relative h-full w-full">
      <MapContainer center={last} zoom={15} className="h-full w-full">
        <AppTileLayer />
        <Polyline positions={positions} pathOptions={{ color: trailColor, weight: 4 }} />
        <PlaceCircles places={places} />
        <HistoryPoints
          points={stays}
          displayedIndex={displayedIndex}
          color={trailColor}
          getKey={(s) => s.anchor_id}
          getRadius={(s) => stayMarkerRadius(s.count)}
          onSelect={onSelectReport ? (s) => onSelectReport(s.anchor_id) : undefined}
        />
        <OwnerTrails histories={ownerLocationHistories} visible={showOwnerTrail} />
        <SelectedPin position={animatedPosition} icon={airtagPinIcon(airtag)} label={displayed.label}>
          <div className={POPUP_WIDTH_CLASS}>
            <p className="mb-2 text-[0.95rem] font-semibold">
              {displayed.label ?? (selectedIndex >= 0 ? 'Ausgewählte Position' : 'Letzte Position')}
            </p>
            <InfoRow icon={<ClockIcon className="h-3.5 w-3.5" />}>
              {displayed.count > 1
                ? `${formatClusterRange(displayed.start, displayed.end)} · ${displayed.count}×`
                : new Date(displayed.start).toLocaleString()}
            </InfoRow>
            {/* Only live-fetch a fallback address when the server has no
                precomputed label (stays.py's resolve_label) - otherwise this
                popup and NoReportsView's would show different info for the
                same kind of "position" depending on which one happened to
                have a cached label yet. */}
            {!displayed.label && <AddressLine lat={displayedPosition[0]} lon={displayedPosition[1]} />}
            <BatteryRow level={displayed.battery_level} />
            <div className="mt-2 flex flex-wrap gap-2">
              <a
                href={mapsUrl(displayedPosition[0], displayedPosition[1], airtag.name)}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded-lg border border-[var(--accent)] px-2.5 py-1.5 text-xs font-medium text-[var(--accent)]"
              >
                <LocationArrowIcon className="h-3.5 w-3.5" />
                In Karten öffnen
              </a>
              <AddPlaceButton
                lat={displayedPosition[0]}
                lon={displayedPosition[1]}
                name={displayed.label}
                onAddPlace={onAddPlace}
              />
            </div>
          </div>
        </SelectedPin>
        {ownerLocations.map((loc) => (
          <Marker
            key={loc.device_id}
            position={[loc.lat, loc.lon]}
            icon={airtagPinIcon({ id: loc.device_id, icon: loc.icon, color: loc.color })}
            eventHandlers={{ click: centerMarkerOnClick }}
          >
            <Popup autoPan={false}>
              <div className={POPUP_WIDTH_CLASS}>
                <p className="mb-2 text-[0.95rem] font-semibold">{loc.name ?? 'Gerät'}</p>
                <InfoRow icon={<ClockIcon className="h-3.5 w-3.5" />}>
                  {capitalize(formatRelative(loc.recorded_at))}
                </InfoRow>
                <AddressLine lat={loc.lat} lon={loc.lon} />
                <BatteryRow level={loc.battery_level} status={loc.battery_status} reported={loc.battery_reported} />
                <div className="mt-2 flex flex-wrap gap-2">
                  {onSelectDevice && (
                    <button
                      type="button"
                      onClick={() => onSelectDevice(loc.device_id)}
                      className="rounded-lg bg-[var(--accent)] px-2.5 py-1.5 text-xs font-medium text-white"
                    >
                      Details anzeigen
                    </button>
                  )}
                  <a
                    href={mapsUrl(loc.lat, loc.lon, loc.name ?? 'Gerät')}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-lg border border-[var(--accent)] px-2.5 py-1.5 text-xs font-medium text-[var(--accent)]"
                  >
                    <LocationArrowIcon className="h-3.5 w-3.5" />
                    In Karten öffnen
                  </a>
                  <AddPlaceButton lat={loc.lat} lon={loc.lon} onAddPlace={onAddPlace} />
                </div>
              </div>
            </Popup>
          </Marker>
        ))}
        {/* FitBounds first, PanToSelection second: FitBounds only re-fires on
            a genuine data change (positions is memoized above) and sets a
            zoom level that fits the whole trail, but PanToSelection - now
            unconditional, not just for an explicit history selection - has
            the final say on centering, so whichever pin is currently
            highlighted (the latest one by default, same as any explicit
            selection) is always what the view actually centers on. */}
        <FitBounds positions={positions} />
        <PanToSelection position={displayedPosition} />
        <InvalidateSizeOnResize />
        <MapClickHandler onMapClick={onMapClick} />
        <FullscreenControl />
        <LocateControl />
        <HeatmapLayer points={stays} />
      </MapContainer>
      {hasOwnerTrails(ownerLocationHistories) && (
        <OwnerTrailToggle visible={showOwnerTrail} onToggle={() => setShowOwnerTrail((v) => !v)} />
      )}
    </div>
  )
}
