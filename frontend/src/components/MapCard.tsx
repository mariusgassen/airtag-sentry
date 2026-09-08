import { useEffect, useRef, useState } from 'react'
import type L from 'leaflet'
import { MapContainer, TileLayer, Polyline, Marker, Popup, useMap } from 'react-leaflet'
import type { Airtag, OwnerLocation, Report } from '../api'
import { getAddress } from '../api'
import { capitalize, formatRelative } from '../format'
import { OWNER_TRAIL_COLOR, airtagPinIcon, currentLocationIcon } from '../mapIcons'
import { mapsUrl } from '../maps'
import { ChevronLeftIcon, ChevronRightIcon, LocationArrowIcon } from './icons'

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
  return <p className="mb-2 text-[var(--text-secondary)]">{address}</p>
}

export function NoReportsView() {
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
}) {
  const positions: [number, number][] = reports.map((r) => [r.lat, r.lon])
  const markerRef = useRef<L.Marker>(null)

  // Pop the marker's popup open when a report is picked from the history
  // list (clicking the map marker itself already opens it via Leaflet).
  useEffect(() => {
    if (selectedReportId != null) markerRef.current?.openPopup()
  }, [selectedReportId])

  if (positions.length === 0) {
    return <NoReportsView />
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
        <Popup>
          <div className="text-sm">
            <p className="mb-1 font-medium">{selectedIndex >= 0 ? 'Ausgewählte Position' : 'Letzte Position'}</p>
            <p className="mb-1 text-[var(--text-secondary)]">{new Date(displayed.timestamp).toLocaleString()}</p>
            <AddressLine lat={displayed.lat} lon={displayed.lon} />
            {onSelectReport && (older || newer) && (
              <div className="mb-2 flex gap-2">
                <button
                  type="button"
                  onClick={() => older && onSelectReport(older.id)}
                  disabled={!older}
                  className="inline-flex flex-1 items-center justify-center gap-1 rounded-lg border border-[var(--accent)] px-2 py-1 text-xs font-medium text-[var(--accent)] disabled:opacity-30"
                >
                  <ChevronLeftIcon className="h-3.5 w-3.5" />
                  Älter
                </button>
                <button
                  type="button"
                  onClick={() => newer && onSelectReport(newer.id)}
                  disabled={!newer}
                  className="inline-flex flex-1 items-center justify-center gap-1 rounded-lg border border-[var(--accent)] px-2 py-1 text-xs font-medium text-[var(--accent)] disabled:opacity-30"
                >
                  Neuer
                  <ChevronRightIcon className="h-3.5 w-3.5" />
                </button>
              </div>
            )}
            <a
              href={mapsUrl(displayedPosition[0], displayedPosition[1], airtag.name)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-lg border border-[var(--accent)] px-2.5 py-1 text-xs font-medium text-[var(--accent)]"
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
            <div className="text-sm">
              <p className="mb-1 font-medium">{loc.name ?? 'Gerät'}</p>
              <p className="mb-2 text-[var(--text-secondary)]">{capitalize(formatRelative(loc.recorded_at))}</p>
              {onSelectDevice && (
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => onSelectDevice(loc.device_id)}
                    className="rounded-lg bg-[var(--accent)] px-2.5 py-1 text-xs font-medium text-white"
                  >
                    Details anzeigen
                  </button>
                  <a
                    href={mapsUrl(loc.lat, loc.lon, loc.name ?? 'Gerät')}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-lg border border-[var(--accent)] px-2.5 py-1 text-xs font-medium text-[var(--accent)]"
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
    </MapContainer>
  )
}
