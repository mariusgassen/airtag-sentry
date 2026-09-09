import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type L from 'leaflet'
import { DomEvent } from 'leaflet'
import { CircleMarker, MapContainer, TileLayer, Polyline, Marker, Popup, useMap, useMapEvent } from 'react-leaflet'
import type { Airtag, OwnerLocation, Report } from '../api'
import { getAddress } from '../api'
import { capitalize, formatRelative } from '../format'
import { OWNER_TRAIL_COLOR, PIN_POPUP_OFFSET, airtagPinIcon, currentLocationIcon, deviceColor } from '../mapIcons'
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

/** Browser geolocation, requested once on mount. Used only as a fallback view
 * for a brand-new AirTag with no reports yet - never overrides real device
 * positions. */
function useCurrentPosition() {
  const [position, setPosition] = useState<[number, number] | null>(null)

  useEffect(() => {
    if (!navigator.geolocation) return
    navigator.geolocation.getCurrentPosition(
      (pos) => setPosition([pos.coords.latitude, pos.coords.longitude]),
      () => setPosition(null),
      { enableHighAccuracy: false, timeout: 10_000 },
    )
  }, [])

  return position
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
  onSelect,
}: {
  points: T[]
  displayedIndex: number
  color: string
  getKey: (point: T, index: number) => string | number
  onSelect?: (point: T) => void
}) {
  return (
    <>
      {points.map((point, i) =>
        i === displayedIndex ? null : (
          <CircleMarker
            key={getKey(point, i)}
            center={[point.lat, point.lon]}
            radius={6}
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
  children,
}: {
  position: [number, number]
  icon: L.DivIcon
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
      />
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
  airtag,
  ownerLocations = [],
  ownerLocationHistories = {},
  onSelectDevice,
  selectedReportId = null,
  onSelectReport,
  onMapClick,
}: {
  reports: Report[]
  airtag: Airtag
  // Current position of every *enabled* owner device (see OwnerDevicesPanel.tsx).
  ownerLocations?: OwnerLocation[]
  // History of every *enabled* device, keyed by device_id - each drawn as its
  // own dashed trail, matching the route the AirTag itself gets.
  ownerLocationHistories?: Record<string, OwnerLocation[]>
  onSelectDevice?: (id: string) => void
  // The report shown as the AirTag's marker/popup - null falls back to the
  // latest one. Selecting a history-list row or stepping older/newer in the
  // mobile title bar (see App.tsx) both flow through this same prop.
  selectedReportId?: number | null
  // Fired when one of the trail's subtle history-point dots is clicked -
  // same selection App.tsx wires up for the sidebar history list, so picking
  // a point on the map behaves identically (centers on it, minimizes the
  // sheet on mobile).
  onSelectReport?: (id: number) => void
  // Fired when the map background (not a marker/popup) is tapped - lets the
  // caller back out to the overview (see App.tsx).
  onMapClick?: () => void
}) {
  // Memoized: reports itself is a stable reference across pure-selection
  // re-renders (App.tsx only replaces it on an actual re-fetch), but
  // `.map()` always returns a fresh array - without this, FitBounds below
  // (keyed on this same array) re-fits the *whole* trail on every render,
  // overriding PanToSelection's explicit centering on every older/newer
  // step or history-list pick.
  const positions = useMemo<[number, number][]>(() => reports.map((r) => [r.lat, r.lon]), [reports])
  const selectedIndex = selectedReportId != null ? reports.findIndex((r) => r.id === selectedReportId) : -1
  const displayedIndex = selectedIndex >= 0 ? selectedIndex : reports.length - 1
  // Undefined when there are no reports at all - only read once positions
  // is confirmed non-empty below, but the hook call itself (Rules of Hooks)
  // has to run unconditionally either way.
  const displayed = reports[displayedIndex] as Report | undefined
  // Memoized: identical lat/lon must keep the same array reference across
  // renders, since it's also the standalone Popup's `position` prop below -
  // react-leaflet fully unbinds/rebinds that popup whenever the reference
  // changes (see the Popup's own comment), so a fresh array every render
  // would reopen it constantly instead of only on a real position change.
  const displayedPosition = useMemo<[number, number]>(
    () => [displayed?.lat ?? 0, displayed?.lon ?? 0],
    [displayed?.lat, displayed?.lon],
  )

  if (positions.length === 0 || !displayed) {
    return <NoReportsView onMapClick={onMapClick} />
  }

  const last = positions[positions.length - 1]
  // This AirTag's own chosen (or hash-derived) color - matches its pin badge
  // so the route it's drawn once selected reads as visually "its own" rather
  // than a generic accent blue (see mapIcons.ts's deviceColor).
  const trailColor = deviceColor(airtag)

  return (
    <MapContainer center={last} zoom={15} className="h-full w-full">
      <TileLayer
        attribution="&copy; OpenStreetMap contributors"
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <Polyline positions={positions} pathOptions={{ color: trailColor, weight: 4 }} />
      <HistoryPoints
        points={reports}
        displayedIndex={displayedIndex}
        color={trailColor}
        getKey={(r) => r.id}
        onSelect={onSelectReport ? (r) => onSelectReport(r.id) : undefined}
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
      <SelectedPin position={displayedPosition} icon={airtagPinIcon(airtag)}>
        <div className={POPUP_WIDTH_CLASS}>
          <p className="mb-2 text-[0.95rem] font-semibold">
            {selectedIndex >= 0 ? 'Ausgewählte Position' : 'Letzte Position'}
          </p>
          <InfoRow icon={<ClockIcon className="h-3.5 w-3.5" />}>
            {new Date(displayed.timestamp).toLocaleString()}
          </InfoRow>
          <AddressLine lat={displayed.lat} lon={displayed.lon} />
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
          {/* autoPan off: centerMarkerOnClick above already centers this
              pin explicitly on click. */}
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
    </MapContainer>
  )
}
