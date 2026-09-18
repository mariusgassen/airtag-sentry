import { useState } from 'react'
import { MapContainer, Marker, Popup } from 'react-leaflet'
import type { Airtag, OwnerLocation, Place, Status } from '../api'
import { capitalize, formatRelative } from '../format'
import { airtagPinIcon, hasOwnerTrails } from '../mapIcons'
import { centerMarkerOnClick, isWithinPlace } from '../maps'
import {
  AddPlaceButton,
  AddressLine,
  AppTileLayer,
  FitBounds,
  FullscreenControl,
  InfoRow,
  InvalidateSizeOnResize,
  LocateControl,
  NoReportsView,
  OpenInMapsButton,
  OwnerTrailToggle,
  OwnerTrails,
  PopupHeader,
  POPUP_WIDTH_CLASS,
} from './MapCard'
import type { AddPlaceHandler } from './MapCard'
import { ClockIcon } from './icons'
import { MarkerClusterGroup } from './MarkerClusterGroup'

interface Props {
  airtags: Airtag[]
  statuses: Record<string, Status>
  onSelect: (id: string) => void
  // Current position of every *enabled* owner device (see OwnerDevicesPanel.tsx).
  ownerLocations?: OwnerLocation[]
  // History of every *enabled* device, keyed by device_id - each optionally
  // drawn as its own trail via OwnerTrailToggle (see MapCard.tsx).
  ownerLocationHistories?: Record<string, OwnerLocation[]>
  onSelectDevice?: (id: string) => void
  onAddPlace?: AddPlaceHandler
  places?: Place[]
}

/** Main map view for the list/settings screens - every AirTag's last known
 * position at once (Find My's own overview screen), vs. MapCard's single
 * tag + route once you've drilled into its detail view. */
export function OverviewMap({
  airtags,
  statuses,
  onSelect,
  ownerLocations = [],
  ownerLocationHistories = {},
  onSelectDevice,
  onAddPlace,
  places = [],
}: Props) {
  const [showOwnerTrail, setShowOwnerTrail] = useState(false)
  const located = airtags
    .map((airtag) => ({ airtag, lastReport: statuses[airtag.id]?.last_report ?? null }))
    .filter((entry): entry is { airtag: Airtag; lastReport: NonNullable<Status['last_report']> } =>
      entry.lastReport !== null,
    )

  // Guarding on AirTags alone hid every device pin on a device-only setup
  // (or before any AirTag has reported yet) - the overview map should still
  // render once there's at least one AirTag *or* device position.
  if (located.length === 0 && ownerLocations.length === 0) {
    return <NoReportsView onAddPlace={onAddPlace} places={places} />
  }

  const positions: [number, number][] = [
    ...located.map(({ lastReport }) => [lastReport.lat, lastReport.lon] as [number, number]),
    ...ownerLocations.map((loc) => [loc.lat, loc.lon] as [number, number]),
  ]

  return (
    <div className="relative h-full w-full">
      <MapContainer center={positions[positions.length - 1]} zoom={13} className="h-full w-full">
        <AppTileLayer />
        <OwnerTrails histories={ownerLocationHistories} visible={showOwnerTrail} />
        <MarkerClusterGroup>
          {located.map(({ airtag, lastReport }) => (
            <Marker
              key={airtag.id}
              position={[lastReport.lat, lastReport.lon]}
              icon={airtagPinIcon(airtag)}
              eventHandlers={{ click: centerMarkerOnClick }}
            >
              {/* autoPan off: centerMarkerOnClick above already centers this
                  pin explicitly on click. */}
              <Popup autoPan={false} closeButton={false}>
                <div className={POPUP_WIDTH_CLASS}>
                  <PopupHeader
                    title={airtag.name}
                    actions={
                      <>
                        <OpenInMapsButton lat={lastReport.lat} lon={lastReport.lon} name={airtag.name} />
                        <AddPlaceButton
                          lat={lastReport.lat}
                          lon={lastReport.lon}
                          onAddPlace={onAddPlace}
                          withinPlace={isWithinPlace(lastReport.lat, lastReport.lon, places)}
                        />
                      </>
                    }
                  />
                  <InfoRow icon={<ClockIcon className="h-3.5 w-3.5" />}>
                    {capitalize(formatRelative(lastReport.timestamp))}
                  </InfoRow>
                  <AddressLine lat={lastReport.lat} lon={lastReport.lon} />
                  <button
                    type="button"
                    onClick={() => onSelect(airtag.id)}
                    className="mt-2 rounded-lg bg-[var(--accent)] px-2.5 py-1.5 text-xs font-medium text-white"
                  >
                    Details anzeigen
                  </button>
                </div>
              </Popup>
            </Marker>
          ))}
          {ownerLocations.map((loc) => (
            <Marker
              key={loc.device_id}
              position={[loc.lat, loc.lon]}
              icon={airtagPinIcon({ id: loc.device_id, icon: loc.icon, color: loc.color })}
              eventHandlers={{ click: centerMarkerOnClick }}
            >
              {/* autoPan off: centerMarkerOnClick above already centers this
                  pin explicitly on click. */}
              <Popup autoPan={false} closeButton={false}>
                <div className={POPUP_WIDTH_CLASS}>
                  <PopupHeader
                    title={loc.name ?? 'Gerät'}
                    actions={
                      <>
                        <OpenInMapsButton lat={loc.lat} lon={loc.lon} name={loc.name ?? 'Gerät'} />
                        <AddPlaceButton
                          lat={loc.lat}
                          lon={loc.lon}
                          onAddPlace={onAddPlace}
                          withinPlace={isWithinPlace(loc.lat, loc.lon, places)}
                        />
                      </>
                    }
                  />
                  <InfoRow icon={<ClockIcon className="h-3.5 w-3.5" />}>
                    {capitalize(formatRelative(loc.recorded_at))}
                  </InfoRow>
                  <AddressLine lat={loc.lat} lon={loc.lon} />
                  {onSelectDevice && (
                    <button
                      type="button"
                      onClick={() => onSelectDevice(loc.device_id)}
                      className="mt-2 rounded-lg bg-[var(--accent)] px-2.5 py-1.5 text-xs font-medium text-white"
                    >
                      Details anzeigen
                    </button>
                  )}
                </div>
              </Popup>
            </Marker>
          ))}
        </MarkerClusterGroup>
        <FitBounds positions={positions} />
        <InvalidateSizeOnResize />
        <FullscreenControl />
        <LocateControl />
      </MapContainer>
      {hasOwnerTrails(ownerLocationHistories) && (
        <OwnerTrailToggle visible={showOwnerTrail} onToggle={() => setShowOwnerTrail((v) => !v)} />
      )}
    </div>
  )
}
