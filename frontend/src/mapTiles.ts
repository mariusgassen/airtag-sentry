/** CARTO's raster basemap tiles (MapCard.tsx's AppTileLayer, SettingsPlaces.tsx,
 * staticMapTile.ts) now require a free API key - anonymous requests get a
 * watermarked tile instead of the real one. Set from App.tsx once GET
 * /api/maps/carto resolves, same live-module-variable pattern as
 * airtagColor.ts's PALETTE: every consumer already re-renders whenever App's
 * state changes, so no context/prop is needed to reach a handful of tile-url
 * builders. Stays null until a key is configured in Settings, in which case
 * every tile URL below falls back to plain OSM tiles instead of a broken one. */
export let CARTO_API_KEY: string | null = null

export function setCartoApiKey(key: string | null): void {
  CARTO_API_KEY = key
}
