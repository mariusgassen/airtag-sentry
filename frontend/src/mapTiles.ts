import type { AppSettings } from './api'

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

/** Settings -> Darstellung's explicit override of the (otherwise automatic)
 * CARTO-vs-OSM choice - see AppSettings.map_tile_provider. 'osm' opts out of
 * CARTO's styling even with a key configured; set from App.tsx alongside
 * color_palette, same live-module-variable pattern as CARTO_API_KEY above. */
export let MAP_TILE_PROVIDER: AppSettings['map_tile_provider'] = 'auto'

export function setMapTileProvider(provider: AppSettings['map_tile_provider']): void {
  MAP_TILE_PROVIDER = provider
}

/** Whether a tile URL should use CARTO (Voyager/Dark Matter) rather than
 * plain OSM - the one condition every tile call site (AppTileLayer,
 * SettingsPlaces.tsx, staticMapTile.ts) needs, kept in one place instead of
 * duplicating the `CARTO_API_KEY && MAP_TILE_PROVIDER !== 'osm'` check three
 * times over. Deliberately not named with a `use` prefix - it's a plain
 * function called from non-component code (staticMapTile.ts), and that
 * prefix would make oxlint's rules-of-hooks treat it as a React Hook. */
export function cartoTilesEnabled(): boolean {
  return CARTO_API_KEY !== null && MAP_TILE_PROVIDER !== 'osm'
}
