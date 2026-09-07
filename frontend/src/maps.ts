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
