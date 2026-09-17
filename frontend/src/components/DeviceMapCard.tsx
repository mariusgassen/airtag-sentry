import { useMemo } from 'react'
import { MapContainer, Polyline } from 'react-leaflet'
import type { LocationStay, OwnerDevice, OwnerLocation, Place } from '../api'
import { deviceLabel, formatClusterRange } from '../format'
import { useAnimatedLatLng } from '../hooks/useAnimatedLatLng'
import { useRoutedTrail } from '../hooks/useRoutedTrail'
import { airtagPinIcon, deviceColor, stayMarkerRadius } from '../mapIcons'
import {
  AddPlaceButton,
  AddressLine,
  AppTileLayer,
  BatteryRow,
  FitBounds,
  FullscreenControl,
  HeatmapLayer,
  HistoryPoints,
  InfoRow,
  InvalidateSizeOnResize,
  LocateControl,
  MapClickHandler,
  NoReportsView,
  OpenInMapsButton,
  PanToSelection,
  PlaceCircles,
  PopupHeader,
  POPUP_WIDTH_CLASS,
  SelectedPin,
} from './MapCard'
import type { AddPlaceHandler } from './MapCard'
import { ClockIcon } from './icons'

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
  stays,
  places = [],
  selectedLocationKey = null,
  onSelectLocation,
  onMapClick,
  onAddPlace,
}: {
  device: OwnerDevice
  locations: OwnerLocation[]
  // Server-computed (see stays.py / GET /api/owner-devices/history).
  stays: LocationStay[]
  places?: Place[]
  selectedLocationKey?: string | null
  onSelectLocation?: (recordedAt: string) => void
  onMapClick?: () => void
  onAddPlace?: AddPlaceHandler
}) {
  // Memoized - see MapCard.tsx's identical comment on its own `positions`.
  const positions = useMemo<[number, number][]>(() => locations.map((l) => [l.lat, l.lon]), [locations])

  const selectedIndex =
    selectedLocationKey != null ? stays.findIndex((s) => s.anchor_recorded_at === selectedLocationKey) : -1
  const displayedIndex = selectedIndex >= 0 ? selectedIndex : 0
  const displayed = stays[displayedIndex] as LocationStay | undefined
  const displayedPosition = useMemo<[number, number]>(
    () => [displayed?.lat ?? 0, displayed?.lon ?? 0],
    [displayed?.lat, displayed?.lon],
  )
  const animatedPosition = useAnimatedLatLng(displayedPosition)
  const routedPositions = useRoutedTrail(positions)

  if (positions.length === 0 || !displayed) {
    return <NoReportsView onMapClick={onMapClick} onAddPlace={onAddPlace} places={places} />
  }

  const trailColor = deviceColor(device)

  return (
    <MapContainer center={displayedPosition} zoom={15} className="h-full w-full">
      <AppTileLayer />
      {positions.length > 1 && (
        <Polyline positions={routedPositions} pathOptions={{ color: trailColor, weight: 4 }} />
      )}
      <PlaceCircles places={places} />
      <HistoryPoints
        points={stays}
        displayedIndex={displayedIndex}
        color={trailColor}
        getKey={(s) => s.anchor_recorded_at}
        getRadius={(s) => stayMarkerRadius(s.count)}
        onSelect={onSelectLocation ? (s) => onSelectLocation(s.anchor_recorded_at) : undefined}
      />
      <SelectedPin position={animatedPosition} icon={airtagPinIcon(device)} label={displayed.label}>
        <div className={POPUP_WIDTH_CLASS}>
          <PopupHeader
            title={displayed.label ?? deviceLabel(device)}
            actions={
              <>
                <OpenInMapsButton lat={displayedPosition[0]} lon={displayedPosition[1]} name={deviceLabel(device)} />
                <AddPlaceButton
                  lat={displayedPosition[0]}
                  lon={displayedPosition[1]}
                  name={displayed.label}
                  onAddPlace={onAddPlace}
                  withinPlace={displayed.place_id != null}
                />
              </>
            }
          />
          <InfoRow icon={<ClockIcon className="h-3.5 w-3.5" />}>
            {displayed.count > 1
              ? `${formatClusterRange(displayed.start, displayed.end)} · ${displayed.count}×`
              : new Date(displayed.start).toLocaleString()}
          </InfoRow>
          {/* See MapCard.tsx's identical comment on its own SelectedPin
              popup - shown even alongside a resolved label, skipped only when
              the label itself already is the raw address. */}
          <AddressLine lat={displayedPosition[0]} lon={displayedPosition[1]} skipIfSame={displayed.label} />
          <BatteryRow level={displayed.battery_level} status={displayed.battery_status} reported={displayed.battery_reported} />
        </div>
      </SelectedPin>
      {/* FitBounds then PanToSelection - see MapCard.tsx's identical comment. */}
      <FitBounds positions={positions} />
      <PanToSelection position={displayedPosition} />
      <InvalidateSizeOnResize />
      <MapClickHandler onMapClick={onMapClick} />
      <FullscreenControl />
      <LocateControl />
      <HeatmapLayer points={stays} />
    </MapContainer>
  )
}
