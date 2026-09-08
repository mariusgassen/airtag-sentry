import { useEffect, useRef } from 'react'
import type L from 'leaflet'
import { MapContainer, TileLayer, Polyline, Marker, Popup } from 'react-leaflet'
import type { OwnerDevice, OwnerLocation } from '../api'
import { deviceLabel } from '../format'
import { OWNER_TRAIL_COLOR, airtagPinIcon } from '../mapIcons'
import { mapsUrl } from '../maps'
import { AddressLine, FitBounds, InvalidateSizeOnResize, NoReportsView, PanToSelection } from './MapCard'
import { ChevronLeftIcon, ChevronRightIcon, LocationArrowIcon } from './icons'

/** Single-device counterpart to MapCard - one owner device's own location
 * trail, drilled into from ObjectsList (device selected -> DeviceDetail).
 * Reuses MapCard's map primitives instead of duplicating them; solid trail
 * (vs. the dashed one OverviewMap/MapCard draw for every *other* tracked
 * device in the background) since this is the one thing being looked at.
 * Selection/prev-next/address behavior mirrors MapCard.tsx exactly - AirTags
 * and owner devices get the same map navigation features (see CLAUDE.md). */
export function DeviceMapCard({
  device,
  locations,
  selectedLocationKey = null,
  onSelectLocation,
}: {
  device: OwnerDevice
  locations: OwnerLocation[]
  // The location shown as the device's marker/popup - null falls back to
  // the latest one. `recorded_at` is the identity key: owner-device
  // locations have no id in the API response, and DeviceHistoryList already
  // keys its rows by it. Selecting a history-list row and stepping
  // Previous/Next in the popup both flow through this same prop.
  selectedLocationKey?: string | null
  onSelectLocation?: (recordedAt: string) => void
}) {
  const positions: [number, number][] = locations.map((l) => [l.lat, l.lon])
  const markerRef = useRef<L.Marker>(null)

  useEffect(() => {
    if (selectedLocationKey != null) markerRef.current?.openPopup()
  }, [selectedLocationKey])

  if (positions.length === 0) {
    return <NoReportsView />
  }

  // /api/owner-devices/history is newest-first (see
  // fetch_owner_device_location_history), unlike AirTag reports - index 0 is
  // the latest fix, and "older" means a *higher* index here.
  const selectedIndex =
    selectedLocationKey != null ? locations.findIndex((l) => l.recorded_at === selectedLocationKey) : -1
  const displayedIndex = selectedIndex >= 0 ? selectedIndex : 0
  const displayed = locations[displayedIndex]
  const displayedPosition: [number, number] = [displayed.lat, displayed.lon]
  const older = displayedIndex < locations.length - 1 ? locations[displayedIndex + 1] : null
  const newer = displayedIndex > 0 ? locations[displayedIndex - 1] : null

  return (
    <MapContainer center={displayedPosition} zoom={15} className="h-full w-full">
      <TileLayer
        attribution="&copy; OpenStreetMap contributors"
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {positions.length > 1 && (
        <Polyline positions={positions} pathOptions={{ color: OWNER_TRAIL_COLOR, weight: 4 }} />
      )}
      <Marker ref={markerRef} position={displayedPosition} icon={airtagPinIcon(device)}>
        <Popup>
          <div className="text-sm">
            <p className="mb-1 font-medium">{deviceLabel(device)}</p>
            <p className="mb-1 text-[var(--text-secondary)]">{new Date(displayed.recorded_at).toLocaleString()}</p>
            <AddressLine lat={displayed.lat} lon={displayed.lon} />
            {onSelectLocation && (older || newer) && (
              <div className="mb-2 flex gap-2">
                <button
                  type="button"
                  onClick={() => older && onSelectLocation(older.recorded_at)}
                  disabled={!older}
                  className="inline-flex flex-1 items-center justify-center gap-1 rounded-lg border border-[var(--accent)] px-2 py-1 text-xs font-medium text-[var(--accent)] disabled:opacity-30"
                >
                  <ChevronLeftIcon className="h-3.5 w-3.5" />
                  Älter
                </button>
                <button
                  type="button"
                  onClick={() => newer && onSelectLocation(newer.recorded_at)}
                  disabled={!newer}
                  className="inline-flex flex-1 items-center justify-center gap-1 rounded-lg border border-[var(--accent)] px-2 py-1 text-xs font-medium text-[var(--accent)] disabled:opacity-30"
                >
                  Neuer
                  <ChevronRightIcon className="h-3.5 w-3.5" />
                </button>
              </div>
            )}
            <a
              href={mapsUrl(displayedPosition[0], displayedPosition[1], deviceLabel(device))}
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
      <PanToSelection position={selectedIndex >= 0 ? displayedPosition : null} />
      <FitBounds positions={positions} />
      <InvalidateSizeOnResize />
    </MapContainer>
  )
}
