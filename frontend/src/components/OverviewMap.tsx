import { MapContainer, TileLayer, Marker, Polyline, Popup } from 'react-leaflet'
import type { Airtag, OwnerLocation, Status } from '../api'
import { capitalize, formatRelative } from '../format'
import { OWNER_TRAIL_COLOR, airtagPinIcon } from '../mapIcons'
import { centerMarkerOnClick, mapsUrl } from '../maps'
import { FitBounds, InfoRow, InvalidateSizeOnResize, NoReportsView, POPUP_WIDTH_CLASS } from './MapCard'
import { ClockIcon, LocationArrowIcon } from './icons'

interface Props {
  airtags: Airtag[]
  statuses: Record<string, Status>
  onSelect: (id: string) => void
  // Current position of every *enabled* owner device (see OwnerDevicesPanel.tsx).
  ownerLocations?: OwnerLocation[]
  // History of every *enabled* device, keyed by device_id - each drawn as its
  // own dashed trail, matching the route AirTags already get.
  ownerLocationHistories?: Record<string, OwnerLocation[]>
  onSelectDevice?: (id: string) => void
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
}: Props) {
  const located = airtags
    .map((airtag) => ({ airtag, lastReport: statuses[airtag.id]?.last_report ?? null }))
    .filter((entry): entry is { airtag: Airtag; lastReport: NonNullable<Status['last_report']> } =>
      entry.lastReport !== null,
    )

  // Guarding on AirTags alone hid every device pin on a device-only setup
  // (or before any AirTag has reported yet) - the overview map should still
  // render once there's at least one AirTag *or* device position.
  if (located.length === 0 && ownerLocations.length === 0) {
    return <NoReportsView />
  }

  const positions: [number, number][] = [
    ...located.map(({ lastReport }) => [lastReport.lat, lastReport.lon] as [number, number]),
    ...ownerLocations.map((loc) => [loc.lat, loc.lon] as [number, number]),
  ]

  return (
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
              </div>
            </div>
          </Popup>
        </Marker>
      ))}
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
      <FitBounds positions={positions} />
      <InvalidateSizeOnResize />
    </MapContainer>
  )
}
