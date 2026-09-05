import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet'
import type { Airtag, Status } from '../api'
import { capitalize, formatRelative } from '../format'
import { FitBounds, InvalidateSizeOnResize, NoReportsView } from './MapCard'

interface Props {
  airtags: Airtag[]
  statuses: Record<string, Status>
  onSelect: (id: string) => void
}

/** Main map view for the list/settings screens - every AirTag's last known
 * position at once (Find My's own overview screen), vs. MapCard's single
 * tag + route once you've drilled into its detail view. */
export function OverviewMap({ airtags, statuses, onSelect }: Props) {
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
        <Marker key={airtag.id} position={[lastReport.lat, lastReport.lon]}>
          <Popup>
            <div className="text-sm">
              <p className="mb-1 font-medium">{airtag.name}</p>
              <p className="mb-2 text-[var(--text-secondary)]">{capitalize(formatRelative(lastReport.timestamp))}</p>
              <button
                type="button"
                onClick={() => onSelect(airtag.id)}
                className="rounded-lg bg-[var(--accent)] px-2.5 py-1 text-xs font-medium text-white"
              >
                Details anzeigen
              </button>
            </div>
          </Popup>
        </Marker>
      ))}
      <FitBounds positions={positions} />
      <InvalidateSizeOnResize />
    </MapContainer>
  )
}
