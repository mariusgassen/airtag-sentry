import type L from 'leaflet'

/** Best-effort deep link to the device's native Maps app for a marker's
 * "open in Maps" popup action. Apple Maps' web URL (`ll` = coordinates, `q` =
 * label) hands off to the native app on iOS/macOS when installed and
 * otherwise just opens as a normal website, so it's a safe default even
 * outside Safari. Everywhere else gets a Google Maps universal link, which
 * hands off to the installed Google Maps app when present. */
export function mapsUrl(lat: number, lon: number, label: string): string {
  const isApple = /Mac|iPhone|iPad|iPod/.test(navigator.userAgent)
  return isApple
    ? `https://maps.apple.com/?ll=${lat},${lon}&q=${encodeURIComponent(label)}`
    : `https://www.google.com/maps/search/?api=1&query=${lat},${lon}`
}

/** Centers the map (without changing zoom) on whichever pin was just
 * clicked - Leaflet's default click behavior only opens the marker's bound
 * popup, autoPanning (where still enabled) just enough to fit the popup
 * rather than truly centering the pin. Wire this to every marker's
 * `eventHandlers.click` (MapCard.tsx, DeviceMapCard.tsx, OverviewMap.tsx). */
export function centerMarkerOnClick(e: L.LeafletMouseEvent) {
  const marker = e.target as L.Marker
  // Leaflet's public Layer API has no "which map is this layer on" getter -
  // `_map` is the actual internal field (TypeScript marks it `protected`
  // only for its own class hierarchy's benefit; Leaflet's own code reads
  // and writes it directly), so reach into it here rather than threading a
  // `useMap()` wrapper component through every marker.
  ;(marker as unknown as { _map?: L.Map })._map?.panTo(marker.getLatLng(), { animate: true })
}
