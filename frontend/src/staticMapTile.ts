import { CARTO_API_KEY, cartoTilesEnabled } from './mapTiles'

/** Single CARTO Voyager (or, with no API key configured yet - see
 * mapTiles.ts - plain OSM) raster tile covering a point, for a small
 * "picture of the place" thumbnail (TimelinePage's VisitRow) - same tile
 * server/attribution the app's live Leaflet maps already use (MapCard.tsx et
 * al.), just picked by hand since a static thumbnail has no react-leaflet
 * MapContainer to ask. One tile (not a cropped/centered composite) is an
 * approximation - the point can land anywhere within it - but it's a real,
 * licensed map image, and every caller marks the <img> loading="lazy" so a
 * long scrolling list doesn't fire every request at once. */
export function staticMapTileUrl(lat: number, lon: number, zoom = 15): string {
  const n = 2 ** zoom
  const latRad = (lat * Math.PI) / 180
  const x = Math.floor(((lon + 180) / 360) * n)
  const y = Math.floor(((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n)
  // Subdomain fixed at "a" - varying it (a/b/c, as the live map does for
  // parallel loading) isn't worth the complexity for single lazy thumbnails.
  return cartoTilesEnabled()
    ? `https://a.basemaps.cartocdn.com/rastertiles/voyager/${zoom}/${x}/${y}.png?api_key=${CARTO_API_KEY}`
    : `https://a.tile.openstreetmap.org/${zoom}/${x}/${y}.png`
}
