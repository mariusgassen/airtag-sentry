import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type L from 'leaflet'
import { DomEvent } from 'leaflet'
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
import { capitalize, formatClusterRange, formatRelative } from '../format'
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
  stayMarkerRadius,
} from '../mapIcons'
import { centerMarkerOnClick, mapsUrl } from '../maps'
import { ClockIcon, LocationArrowIcon, MapPinIcon } from './icons'

// Every marker popup in the app (this file, DeviceMapCard.tsx, OverviewMap.tsx)
// shares this shape - a fixed width so the card doesn't reflow oddly between
// a short ("Letzte Position" only) and a long (address + prev/next) variant.
export const POPUP_WIDTH_CLASS = 'w-60'

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

export function NoReportsView({ onMapClick }: { onMapClick?: () => void } = {}) {
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
      <TileLayer
        attribution="&copy; OpenStreetMap contributors"
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
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
            <a
              href={mapsUrl(here[0], here[1], 'Aktueller Standort')}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 flex items-center justify-center gap-1.5 rounded-lg border border-[var(--accent)] px-3 py-1.5 text-xs font-medium text-[var(--accent)]"
            >
              <LocationArrowIcon className="h-3.5 w-3.5" />
              In Karten öffnen
            </a>
          </div>
        </Popup>
      </Marker>
      <MapClickHandler onMapClick={onMapClick} />
      <InvalidateSizeOnResize />
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
}) {
  const positions = useMemo<[number, number][]>(() => reports.map((r) => [r.lat, r.lon]), [reports])
  const selectedIndex = selectedReportId != null ? stays.findIndex((s) => s.anchor_id === selectedReportId) : -1
  const displayedIndex = selectedIndex >= 0 ? selectedIndex : stays.length - 1
  const displayed = stays[displayedIndex] as ReportStay | undefined
  const displayedPosition = useMemo<[number, number]>(
    () => [displayed?.lat ?? 0, displayed?.lon ?? 0],
    [displayed?.lat, displayed?.lon],
  )
  const animatedPosition = useAnimatedLatLng(displayedPosition)

  if (positions.length === 0 || !displayed) {
    return <NoReportsView onMapClick={onMapClick} />
  }

  const last = positions[positions.length - 1]
  const trailColor = deviceColor(airtag)

  return (
    <MapContainer center={last} zoom={15} className="h-full w-full">
      <TileLayer
        attribution="&copy; OpenStreetMap contributors"
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
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
      {Object.entries(ownerLocationHistories).map(([deviceId, history]) => {
        const ownerPositions: [number, number][] = history.map((l) => [l.lat, l.lon])
        if (ownerPositions.length < 2) return null
        return (
          <Polyline
            key={deviceId}
            positions={ownerPositions}
            pathOptions={{ color: OWNER_TRAIL_COLOR, weight: 3, dashArray: '6 6' }}
          />
        )
      })}
      <SelectedPin position={animatedPosition} icon={airtagPinIcon(airtag)} label={displayed.label}>
        <div className={POPUP_WIDTH_CLASS}>
          <p className="mb-2 text-[0.95rem] font-semibold">
            {selectedIndex >= 0 ? 'Ausgewählte Position' : 'Letzte Position'}
          </p>
          <InfoRow icon={<ClockIcon className="h-3.5 w-3.5" />}>
            {displayed.count > 1
              ? `${formatClusterRange(displayed.start, displayed.end)} · ${displayed.count}×`
              : new Date(displayed.start).toLocaleString()}
          </InfoRow>
          {displayed.label && (
            <InfoRow icon={<MapPinIcon className="h-3.5 w-3.5" />}>{displayed.label}</InfoRow>
          )}
          <a
            href={mapsUrl(displayedPosition[0], displayedPosition[1], airtag.name)}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 flex items-center justify-center gap-1.5 rounded-lg border border-[var(--accent)] px-3 py-1.5 text-xs font-medium text-[var(--accent)]"
          >
            <LocationArrowIcon className="h-3.5 w-3.5" />
            In Karten öffnen
          </a>
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
              {onSelectDevice && (
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => onSelectDevice(loc.device_id)}
                    className="rounded-lg bg-[var(--accent)] px-2.5 py-1.5 text-xs font-medium text-white"
                  >
                    Details anzeigen
                  </button>
                  <a
                    href={mapsUrl(loc.lat, loc.lon, loc.name ?? 'Gerät')}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-lg border border-[var(--accent)] px-2.5 py-1.5 text-xs font-medium text-[var(--accent)]"
                  >
                    <LocationArrowIcon className="h-3.5 w-3.5" />
                    In Karten öffnen
                  </a>
                </div>
              )}
            </div>
          </Popup>
        </Marker>
      ))}
      <FitBounds positions={positions} />
      <PanToSelection position={displayedPosition} />
      <InvalidateSizeOnResize />
      <MapClickHandler onMapClick={onMapClick} />
    </MapContainer>
  )
}
