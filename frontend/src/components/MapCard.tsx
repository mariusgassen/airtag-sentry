import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type L from 'leaflet'
import { MapContainer, TileLayer, Polyline, Marker, Popup, useMap, useMapEvent } from 'react-leaflet'
import type { Airtag, OwnerLocation, Report } from '../api'
import { getAddress } from '../api'
import { capitalize, formatRelative } from '../format'
import { OWNER_TRAIL_COLOR, airtagPinIcon, currentLocationIcon } from '../mapIcons'
import { mapsUrl } from '../maps'
import { ChevronDownIcon, ChevronUpIcon, ClockIcon, LocationArrowIcon, MapPinIcon } from './icons'

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

/** Timestamp/address info paired with the older/newer stepper (^ / v
 * arrows), grouped at the top of a "selected pin" popup - previously the
 * stepper sat at the bottom as separate left/right "Älter"/"Neuer" buttons,
 * disconnected from the info it steps through. Pass null (not omitted) for
 * a direction with nothing to step to, so its button renders disabled
 * rather than disappearing and shifting the other one. Exported for
 * DeviceMapCard.tsx, which shares this same popup content. */
export function PopupStepper({
  timestamp,
  lat,
  lon,
  onOlder,
  onNewer,
}: {
  timestamp: string
  lat: number
  lon: number
  onOlder?: (() => void) | null
  onNewer?: (() => void) | null
}) {
  return (
    <div className="mb-2 flex items-start justify-between gap-3">
      <div className="min-w-0 flex-1">
        <InfoRow icon={<ClockIcon className="h-3.5 w-3.5" />}>{new Date(timestamp).toLocaleString()}</InfoRow>
        <AddressLine lat={lat} lon={lon} />
      </div>
      {(onOlder || onNewer) && (
        <div className="flex shrink-0 flex-col gap-0.5 rounded-lg bg-[var(--surface-2)] p-1">
          <button
            type="button"
            onClick={() => onNewer?.()}
            disabled={!onNewer}
            aria-label="Neuerer Standort"
            title="Neuerer Standort"
            className="rounded-md p-1 text-[var(--text)] disabled:opacity-30"
          >
            <ChevronUpIcon className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => onOlder?.()}
            disabled={!onOlder}
            aria-label="Älterer Standort"
            title="Älterer Standort"
            className="rounded-md p-1 text-[var(--text)] disabled:opacity-30"
          >
            <ChevronDownIcon className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  )
}

export function FitBounds({ positions }: { positions: [number, number][] }) {
  const map = useMap()
  useEffect(() => {
    if (positions.length > 0) {
      map.fitBounds(positions, { padding: [24, 24] })
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

/** Pans (without changing zoom) to an explicitly-selected report's position -
 * separate from FitBounds, which only reframes the whole trail when the
 * report list itself changes, not on every selection. Exported for
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
      <Marker position={here} icon={currentLocationIcon}>
        <Popup>Aktueller Standort</Popup>
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
  // latest one. Selecting a history-list row and stepping Previous/Next in
  // the popup both flow through this same prop (see App.tsx).
  selectedReportId?: number | null
  onSelectReport?: (id: number) => void
  // Fired when the map background (not a marker/popup) is tapped - lets the
  // caller back out to the overview (see App.tsx).
  onMapClick?: () => void
}) {
  const positions: [number, number][] = reports.map((r) => [r.lat, r.lon])
  const markerRef = useRef<L.Marker>(null)

  // Pop the marker's popup open when a report is picked from the history
  // list (clicking the map marker itself already opens it via Leaflet).
  useEffect(() => {
    if (selectedReportId != null) markerRef.current?.openPopup()
  }, [selectedReportId])

  if (positions.length === 0) {
    return <NoReportsView onMapClick={onMapClick} />
  }

  const last = positions[positions.length - 1]
  const selectedIndex = selectedReportId != null ? reports.findIndex((r) => r.id === selectedReportId) : -1
  const displayedIndex = selectedIndex >= 0 ? selectedIndex : reports.length - 1
  const displayed = reports[displayedIndex]
  const displayedPosition: [number, number] = [displayed.lat, displayed.lon]
  const older = displayedIndex > 0 ? reports[displayedIndex - 1] : null
  const newer = displayedIndex < reports.length - 1 ? reports[displayedIndex + 1] : null

  return (
    <MapContainer center={last} zoom={15} className="h-full w-full">
      <TileLayer
        attribution="&copy; OpenStreetMap contributors"
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <Polyline positions={positions} pathOptions={{ color: '#0a84ff', weight: 4 }} />
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
      <Marker ref={markerRef} position={displayedPosition} icon={airtagPinIcon(airtag)}>
        {/* autoPan off: PanToSelection below already centers the selected
            pin explicitly, and its pan runs before this popup opens (child
            effects flush before this component's own openPopup effect) -
            Leaflet's own autoPan would otherwise re-shift the view to fit
            the popup afterwards, undoing that centering (see CLAUDE.md's
            map-navigation-experience note on AirTag/device parity - this
            fix and DeviceMapCard's mirror it exactly). */}
        <Popup autoPan={false}>
          <div className={POPUP_WIDTH_CLASS}>
            <p className="mb-2 text-[0.95rem] font-semibold">
              {selectedIndex >= 0 ? 'Ausgewählte Position' : 'Letzte Position'}
            </p>
            <PopupStepper
              timestamp={displayed.timestamp}
              lat={displayed.lat}
              lon={displayed.lon}
              onOlder={onSelectReport ? (older ? () => onSelectReport(older.id) : null) : undefined}
              onNewer={onSelectReport ? (newer ? () => onSelectReport(newer.id) : null) : undefined}
            />
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
        </Popup>
      </Marker>
      {ownerLocations.map((loc) => (
        <Marker
          key={loc.device_id}
          position={[loc.lat, loc.lon]}
          icon={airtagPinIcon({ id: loc.device_id, icon: loc.icon, color: loc.color })}
        >
          <Popup>
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
      <PanToSelection position={selectedIndex >= 0 ? displayedPosition : null} />
      <FitBounds positions={positions} />
      <InvalidateSizeOnResize />
      <MapClickHandler onMapClick={onMapClick} />
    </MapContainer>
  )
}
