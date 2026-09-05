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

export function MapCard({ reports }: { reports: Report[] }) {
  const positions: [number, number][] = reports.map((r) => [r.lat, r.lon])

  return (
    <section className="overflow-hidden rounded-2xl border border-white/10 bg-[#161b22] shadow-lg">
      <div className="h-[55vh] min-h-[320px] w-full">
        {positions.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-[#8b949e]">
            Keine Standortdaten vorhanden.
          </div>
        ) : (
          <MapContainer center={positions[positions.length - 1]} zoom={15} className="h-full w-full">
            <TileLayer
              attribution="&copy; OpenStreetMap contributors"
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            <Polyline positions={positions} pathOptions={{ color: '#1f6feb', weight: 4 }} />
            <Marker position={positions[positions.length - 1]}>
              <Popup>Letzte Position</Popup>
            </Marker>
            <FitBounds positions={positions} />
          </MapContainer>
        )}
      </div>
    </section>
  )
}
