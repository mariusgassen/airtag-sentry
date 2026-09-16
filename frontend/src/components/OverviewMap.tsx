import { useState } from 'react'
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet'
import type { Airtag, OwnerLocation, Status } from '../api'
import { capitalize, formatRelative } from '../format'
import { airtagPinIcon, hasOwnerTrails } from '../mapIcons'
import { centerMarkerOnClick, mapsUrl } from '../maps'
import {
  AddPlaceButton,
  AddressLine,
  FitBounds,
  InfoRow,
  InvalidateSizeOnResize,
  NoReportsView,
  OwnerTrailToggle,
  OwnerTrails,
  POPUP_WIDTH_CLASS,
} from './MapCard'
import type { AddPlaceHandler } from './MapCard'
import { ClockIcon, LocationArrowIcon } from './icons'

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
    return <NoReportsView onAddPlace={onAddPlace} />
  }

  const positions: [number, number][] = [
    ...located.map(({ lastReport }) => [lastReport.lat, lastReport.lon] as [number, number]),
    ...ownerLocations.map((loc) => [loc.lat, loc.lon] as [number, number]),
  ]

  return (
    <div className="relative h-full w-full">
      <MapContainer center={positions[positions.length - 1]} zoom={13} className="h-full w-full">
        <TileLayer
          attribution="&copy; OpenStreetMap contributors"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {located.map(({ airtag, lastReport }) => (
          <Marker
            key={airtag.id}
            position={[lastReport.lat, lastReport.lon]}
            icon={airtagPinIcon(airtag)}
            eventHandlers={{ click: centerMarkerOnClick }}
          >
            {/* autoPan off: centerMarkerOnClick above already centers this
                pin explicitly on click. */}
            <Popup autoPan={false}>
              <div className={POPUP_WIDTH_CLASS}>
                <p className="mb-2 text-[0.95rem] font-semibold">{airtag.name}</p>
                <InfoRow icon={<ClockIcon className="h-3.5 w-3.5" />}>
                  {capitalize(formatRelative(lastReport.timestamp))}
                </InfoRow>
                <AddressLine lat={lastReport.lat} lon={lastReport.lon} />
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => onSelect(airtag.id)}
                    className="rounded-lg bg-[var(--accent)] px-2.5 py-1.5 text-xs font-medium text-white"
                  >
                    Details anzeigen
                  </button>
                  <a
                    href={mapsUrl(lastReport.lat, lastReport.lon, airtag.name)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-lg border border-[var(--accent)] px-2.5 py-1.5 text-xs font-medium text-[var(--accent)]"
                  >
                    <LocationArrowIcon className="h-3.5 w-3.5" />
                    In Karten öffnen
                  </a>
                  <AddPlaceButton lat={lastReport.lat} lon={lastReport.lon} onAddPlace={onAddPlace} />
                </div>
              </div>
            </Popup>
          </Marker>
        ))}
        <OwnerTrails histories={ownerLocationHistories} visible={showOwnerTrail} />
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
                <AddressLine lat={loc.lat} lon={loc.lon} />
                <div className="mt-2 flex flex-wrap gap-2">
                  {onSelectDevice && (
                    <button
                      type="button"
                      onClick={() => onSelectDevice(loc.device_id)}
                      className="rounded-lg bg-[var(--accent)] px-2.5 py-1.5 text-xs font-medium text-white"
                    >
                      Details anzeigen
                    </button>
                  )}
                  <a
                    href={mapsUrl(loc.lat, loc.lon, loc.name ?? 'Gerät')}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-lg border border-[var(--accent)] px-2.5 py-1.5 text-xs font-medium text-[var(--accent)]"
                  >
                    <LocationArrowIcon className="h-3.5 w-3.5" />
                    In Karten öffnen
                  </a>
                  <AddPlaceButton lat={loc.lat} lon={loc.lon} onAddPlace={onAddPlace} />
                </div>
              </div>
            </Popup>
          </Marker>
        ))}
        <FitBounds positions={positions} />
        <InvalidateSizeOnResize />
      </MapContainer>
      {hasOwnerTrails(ownerLocationHistories) && (
        <OwnerTrailToggle visible={showOwnerTrail} onToggle={() => setShowOwnerTrail((v) => !v)} />
      )}
    </div>
  )
}
