import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, Polyline, Marker, Popup, useMap } from 'react-leaflet'
import type { Airtag, OwnerLocation, Report } from '../api'
import { formatRelative } from '../format'
import { airtagPinIcon, currentLocationIcon } from '../mapIcons'
import { mapsUrl } from '../maps'
import { LocationArrowIcon } from './icons'

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
  ownerLocation,
}: {
  reports: Report[]
  airtag: Airtag
  ownerLocation?: OwnerLocation | null
}) {
  const positions: [number, number][] = reports.map((r) => [r.lat, r.lon])

  if (positions.length === 0) {
    return <NoReportsView />
  }

  const last = positions[positions.length - 1]

  return (
    <MapContainer center={last} zoom={15} className="h-full w-full">
      <TileLayer
        attribution="&copy; OpenStreetMap contributors"
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <Polyline positions={positions} pathOptions={{ color: '#0a84ff', weight: 4 }} />
      <Marker position={last} icon={airtagPinIcon(airtag)}>
        <Popup>
          <div className="text-sm">
            <p className="mb-2 font-medium">Letzte Position</p>
            <a
              href={mapsUrl(last[0], last[1], airtag.name)}
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
      {ownerLocation && (
        <Marker position={[ownerLocation.lat, ownerLocation.lon]} icon={currentLocationIcon}>
          <Popup>Eigener Standort · {formatRelative(ownerLocation.recorded_at)}</Popup>
        </Marker>
      )}
      <FitBounds positions={positions} />
      <InvalidateSizeOnResize />
    </MapContainer>
  )
}
