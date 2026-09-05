import { useEffect } from 'react'
import { MapContainer, TileLayer, Polyline, Marker, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'
import type { Report } from '../api'

// Leaflet's default marker icon references relative image paths that don't
// resolve through Vite's bundler - point them at the bundled asset URLs.
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
})

function FitBounds({ positions }: { positions: [number, number][] }) {
  const map = useMap()
  useEffect(() => {
    if (positions.length > 0) {
      map.fitBounds(positions, { padding: [24, 24] })
    }
  }, [map, positions])
  return null
}

/**
 * Leaflet caches its container size and only recalculates on window
 * `resize`. This two-pane layout resizes the map's container via CSS alone
 * (sidebar toggling, breakpoint changes) without the window itself
 * resizing, which otherwise leaves the map rendering into a stale-size box
 * (grey bands / misaligned tiles) - watch the container directly instead.
 */
function InvalidateSizeOnResize() {
  const map = useMap()
  useEffect(() => {
    const container = map.getContainer()
    const observer = new ResizeObserver(() => map.invalidateSize())
    observer.observe(container)
    return () => observer.disconnect()
  }, [map])
  return null
}

export function MapCard({ reports }: { reports: Report[] }) {
  const positions: [number, number][] = reports.map((r) => [r.lat, r.lon])

  if (positions.length === 0) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-[var(--surface)] text-sm text-[var(--text-secondary)]">
        Keine Standortdaten vorhanden.
      </div>
    )
  }

  return (
    <MapContainer center={positions[positions.length - 1]} zoom={15} className="h-full w-full">
      <TileLayer
        attribution="&copy; OpenStreetMap contributors"
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <Polyline positions={positions} pathOptions={{ color: '#0a84ff', weight: 4 }} />
      <Marker position={positions[positions.length - 1]}>
        <Popup>Letzte Position</Popup>
      </Marker>
      <FitBounds positions={positions} />
      <InvalidateSizeOnResize />
    </MapContainer>
  )
}
