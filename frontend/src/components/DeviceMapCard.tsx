import { useMemo } from 'react'
import { MapContainer, TileLayer, Polyline } from 'react-leaflet'
import type { OwnerDevice, OwnerLocation } from '../api'
import { clusterByProximity } from '../clustering'
import { deviceLabel, formatClusterRange, formatDateTime } from '../format'
import { useAnimatedLatLng } from '../hooks/useAnimatedLatLng'
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
  clusterRadiusMeters,
  selectedLocationKey = null,
  onSelectLocation,
  onMapClick,
}: {
  device: OwnerDevice
  locations: OwnerLocation[]
  // "Same spot" radius for collapsing consecutive locations into one stay -
  // see clustering.ts and AppSettings.history_cluster_radius_meters.
  clusterRadiusMeters: number
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
  // Collapses consecutive same-spot locations into "stays" - see
  // clustering.ts. Mirrors MapCard.tsx's identical clusters/clusterByReportId
  // pair (see CLAUDE.md's AirTag/device parity constraint), keyed by
  // recorded_at since OwnerLocation has no id.
  const clusters = useMemo(
    () => clusterByProximity(locations, (l) => [l.lat, l.lon], clusterRadiusMeters),
    [locations, clusterRadiusMeters],
  )
  const clusterByRecordedAt = useMemo(() => {
    const map = new Map<string, (typeof clusters)[number]>()
    for (const c of clusters) for (const p of c.points) map.set(p.recorded_at, c)
    return map
  }, [clusters])

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
  // See MapCard.tsx's identical comment on its own displayedCluster/pinReport.
  const displayedCluster = useMemo(
    () => (displayed ? clusterByRecordedAt.get(displayed.recorded_at) : undefined),
    [clusterByRecordedAt, displayed],
  )
  const pinLocation = useMemo(() => displayedCluster?.anchor ?? displayed, [displayedCluster, displayed])
  // Memoized: see MapCard.tsx's identical comment on its own displayedPosition.
  const displayedPosition = useMemo<[number, number]>(
    () => [pinLocation?.lat ?? 0, pinLocation?.lon ?? 0],
    [pinLocation?.lat, pinLocation?.lon],
  )
  // See MapCard.tsx's identical comment on its own animatedPosition/
  // useAnimatedLatLng - PanToSelection below still targets the raw
  // displayedPosition.
  const animatedPosition = useAnimatedLatLng(displayedPosition)

  if (positions.length === 0 || !displayed) {
    return <NoReportsView onMapClick={onMapClick} />
  }

  // This device's own chosen (or hash-derived) color - matches MapCard.tsx's
  // identical trailColor for an AirTag, see the comment there.
  const trailColor = deviceColor(device)
  // See MapCard.tsx's identical comment on its own resolvedPinReport.
  const resolvedPinLocation = pinLocation ?? displayed

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
        points={clusters.map((c) => c.anchor)}
        displayedIndex={displayedCluster ? clusters.indexOf(displayedCluster) : -1}
        color={trailColor}
        getKey={(l) => l.recorded_at}
        onSelect={onSelectLocation ? (l) => onSelectLocation(l.recorded_at) : undefined}
      />
      {/* Marker + popup mirrors MapCard.tsx's SelectedPin exactly, see the
          comment there for why it isn't a plain bound Marker/Popup pair. */}
      <SelectedPin position={animatedPosition} icon={airtagPinIcon(device)}>
        <div className={POPUP_WIDTH_CLASS}>
          <p className="mb-2 text-[0.95rem] font-semibold">{deviceLabel(device)}</p>
          <InfoRow icon={<ClockIcon className="h-3.5 w-3.5" />}>
            {displayedCluster && displayedCluster.points.length > 1
              ? `${formatClusterRange(displayedCluster.points[displayedCluster.points.length - 1].recorded_at, displayedCluster.points[0].recorded_at)} · ${displayedCluster.points.length}×`
              : formatDateTime(resolvedPinLocation.recorded_at)}
          </InfoRow>
          <AddressLine lat={resolvedPinLocation.lat} lon={resolvedPinLocation.lon} />
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
