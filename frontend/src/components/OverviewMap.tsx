import { MapContainer, TileLayer, Marker, Polyline, Popup } from 'react-leaflet'
import type { Airtag, OwnerLocation, Status } from '../api'
import { capitalize, formatRelative } from '../format'
import { OWNER_TRAIL_COLOR, airtagPinIcon, currentLocationIcon } from '../mapIcons'
import { mapsUrl } from '../maps'
import { FitBounds, InvalidateSizeOnResize, NoReportsView } from './MapCard'
import { LocationArrowIcon } from './icons'

interface Props {
  airtags: Airtag[]
  statuses: Record<string, Status>
  onSelect: (id: string) => void
  ownerLocation?: OwnerLocation | null
  ownerLocationHistory?: OwnerLocation[]
}

/** Main map view for the list/settings screens - every AirTag's last known
 * position at once (Find My's own overview screen), vs. MapCard's single
 * tag + route once you've drilled into its detail view. */
export function OverviewMap({ airtags, statuses, onSelect, ownerLocation, ownerLocationHistory }: Props) {
  const ownerPositions: [number, number][] = (ownerLocationHistory ?? []).map((l) => [l.lat, l.lon])
  const located = airtags
    .map((airtag) => ({ airtag, lastReport: statuses[airtag.id]?.last_report ?? null }))
    .filter((entry): entry is { airtag: Airtag; lastReport: NonNullable<Status['last_report']> } =>
      entry.lastReport !== null,
    )

  if (located.length === 0) {
    return <NoReportsView />
  }

  const positions: [number, number][] = located.map(({ lastReport }) => [lastReport.lat, lastReport.lon])

  return (
    <MapContainer center={positions[positions.length - 1]} zoom={13} className="h-full w-full">
      <TileLayer
        attribution="&copy; OpenStreetMap contributors"
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {located.map(({ airtag, lastReport }) => (
        <Marker key={airtag.id} position={[lastReport.lat, lastReport.lon]} icon={airtagPinIcon(airtag)}>
          <Popup>
            <div className="text-sm">
              <p className="mb-1 font-medium">{airtag.name}</p>
              <p className="mb-2 text-[var(--text-secondary)]">{capitalize(formatRelative(lastReport.timestamp))}</p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => onSelect(airtag.id)}
                  className="rounded-lg bg-[var(--accent)] px-2.5 py-1 text-xs font-medium text-white"
                >
                  Details anzeigen
                </button>
                <a
                  href={mapsUrl(lastReport.lat, lastReport.lon, airtag.name)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 rounded-lg border border-[var(--accent)] px-2.5 py-1 text-xs font-medium text-[var(--accent)]"
                >
                  <LocationArrowIcon className="h-3.5 w-3.5" />
                  In Karten öffnen
                </a>
              </div>
            </div>
          </Popup>
        </Marker>
      ))}
      {ownerPositions.length > 1 && (
        <Polyline positions={ownerPositions} pathOptions={{ color: OWNER_TRAIL_COLOR, weight: 3, dashArray: '6 6' }} />
      )}
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
