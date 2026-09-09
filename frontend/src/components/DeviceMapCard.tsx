import { useMemo } from 'react'
import { MapContainer, TileLayer, Polyline } from 'react-leaflet'
import type { OwnerDevice, OwnerLocation } from '../api'
import { deviceLabel } from '../format'
import { airtagPinIcon, deviceColor } from '../mapIcons'
import { mapsUrl } from '../maps'
import {
  AddressLine,
  FitBounds,
  HistoryPoints,
  InfoRow,
  InvalidateSizeOnResize,
  MapClickHandler,
  NoReportsView,
  PanToSelection,
  POPUP_WIDTH_CLASS,
  SelectedPin,
} from './MapCard'
import { ClockIcon, LocationArrowIcon } from './icons'

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
  onMapClick,
}: {
  device: OwnerDevice
  locations: OwnerLocation[]
  // The location shown as the device's marker/popup - null falls back to
  // the latest one. `recorded_at` is the identity key: owner-device
  // locations have no id in the API response, and DeviceHistoryList already
  // keys its rows by it. Selecting a history-list row or stepping
  // older/newer in the mobile title bar (see App.tsx) both flow through
  // this same prop.
  selectedLocationKey?: string | null
  // Fired when one of the trail's subtle history-point dots is clicked -
  // mirrors MapCard.tsx's onSelectReport exactly (see CLAUDE.md's
  // AirTag/device parity constraint).
  onSelectLocation?: (recordedAt: string) => void
  // Fired when the map background (not a marker/popup) is tapped - lets the
  // caller back out to the overview (see App.tsx).
  onMapClick?: () => void
}) {
  // Memoized: see MapCard.tsx's identical comment on its own positions -
  // without this, FitBounds below re-fits the *whole* trail on every
  // render, overriding PanToSelection's explicit centering on every
  // older/newer step or history-list pick.
  const positions = useMemo<[number, number][]>(() => locations.map((l) => [l.lat, l.lon]), [locations])

  // /api/owner-devices/history is newest-first (see
  // fetch_owner_device_location_history), unlike AirTag reports - index 0 is
  // the latest fix, and "older" means a *higher* index here.
  const selectedIndex =
    selectedLocationKey != null ? locations.findIndex((l) => l.recorded_at === selectedLocationKey) : -1
  const displayedIndex = selectedIndex >= 0 ? selectedIndex : 0
  // Undefined when there are no locations at all - only read once positions
  // is confirmed non-empty below, but the hook call itself (Rules of Hooks)
  // has to run unconditionally either way.
  const displayed = locations[displayedIndex] as OwnerLocation | undefined
  // Memoized: see MapCard.tsx's identical comment on its own displayedPosition.
  const displayedPosition = useMemo<[number, number]>(
    () => [displayed?.lat ?? 0, displayed?.lon ?? 0],
    [displayed?.lat, displayed?.lon],
  )

  if (positions.length === 0 || !displayed) {
    return <NoReportsView onMapClick={onMapClick} />
  }

  // This device's own chosen (or hash-derived) color - matches MapCard.tsx's
  // identical trailColor for an AirTag, see the comment there.
  const trailColor = deviceColor(device)

  return (
    <MapContainer center={displayedPosition} zoom={15} className="h-full w-full">
      <TileLayer
        attribution="&copy; OpenStreetMap contributors"
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {positions.length > 1 && (
        <Polyline positions={positions} pathOptions={{ color: trailColor, weight: 4 }} />
      )}
      <HistoryPoints
        points={locations}
        displayedIndex={displayedIndex}
        color={trailColor}
        getKey={(l) => l.recorded_at}
        onSelect={onSelectLocation ? (l) => onSelectLocation(l.recorded_at) : undefined}
      />
      {/* Marker + popup mirrors MapCard.tsx's SelectedPin exactly, see the
          comment there for why it isn't a plain bound Marker/Popup pair. */}
      <SelectedPin position={displayedPosition} icon={airtagPinIcon(device)}>
        <div className={POPUP_WIDTH_CLASS}>
          <p className="mb-2 text-[0.95rem] font-semibold">{deviceLabel(device)}</p>
          <InfoRow icon={<ClockIcon className="h-3.5 w-3.5" />}>
            {new Date(displayed.recorded_at).toLocaleString()}
          </InfoRow>
          <AddressLine lat={displayed.lat} lon={displayed.lon} />
          <a
            href={mapsUrl(displayedPosition[0], displayedPosition[1], deviceLabel(device))}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 flex items-center justify-center gap-1.5 rounded-lg border border-[var(--accent)] px-3 py-1.5 text-xs font-medium text-[var(--accent)]"
          >
            <LocationArrowIcon className="h-3.5 w-3.5" />
            In Karten öffnen
          </a>
        </div>
      </SelectedPin>
      {/* FitBounds first, PanToSelection second: mirrors MapCard.tsx's own
          ordering exactly, see the comment there for why. */}
      <FitBounds positions={positions} />
      <PanToSelection position={displayedPosition} />
      <InvalidateSizeOnResize />
      <MapClickHandler onMapClick={onMapClick} />
    </MapContainer>
  )
}
