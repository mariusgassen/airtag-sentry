import { MapContainer, TileLayer, Polyline, Marker, Popup } from 'react-leaflet'
import type { OwnerDevice, OwnerLocation } from '../api'
import { OWNER_TRAIL_COLOR, currentLocationIcon } from '../mapIcons'
import { mapsUrl } from '../maps'
import { FitBounds, InvalidateSizeOnResize, NoReportsView } from './MapCard'
import { LocationArrowIcon } from './icons'

/** Single-device counterpart to MapCard - one owner device's own location
 * trail, drilled into from ObjectsList (device selected -> DeviceDetail).
 * Reuses MapCard's map primitives instead of duplicating them; solid trail
 * (vs. the dashed one OverviewMap/MapCard draw for every *other* tracked
 * device in the background) since this is the one thing being looked at. */
export function DeviceMapCard({ device, locations }: { device: OwnerDevice; locations: OwnerLocation[] }) {
  const positions: [number, number][] = locations.map((l) => [l.lat, l.lon])

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
      {positions.length > 1 && (
        <Polyline positions={positions} pathOptions={{ color: OWNER_TRAIL_COLOR, weight: 4 }} />
      )}
      <Marker position={last} icon={currentLocationIcon}>
        <Popup>
          <div className="text-sm">
            <p className="mb-2 font-medium">{device.name}</p>
            <a
              href={mapsUrl(last[0], last[1], device.name)}
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
      <FitBounds positions={positions} />
      <InvalidateSizeOnResize />
    </MapContainer>
  )
}
