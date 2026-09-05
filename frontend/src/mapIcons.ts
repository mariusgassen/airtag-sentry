import L from 'leaflet'
import { airtagColor } from './airtagColor'

const SIZE = 32

// Mirrors AirtagGlyph's two-concentric-circle look, inlined as a raw SVG
// string since divIcon content is plain HTML rather than React.
const GLYPH_SVG = `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
  <circle cx="12" cy="12" r="6.5" stroke="white" stroke-width="1.6"/>
  <circle cx="12" cy="12" r="2" fill="white"/>
</svg>`

/** A colored circular badge pin for an AirTag's map marker, matching the
 * same airtagColor(id) used for its list/detail avatar so an item reads as
 * the same item on the map as it does in the list. */
export function airtagPinIcon(id: string): L.DivIcon {
  const color = airtagColor(id)
  return L.divIcon({
    className: 'airtag-pin',
    html: `
      <span class="airtag-pin__badge" style="width:${SIZE}px;height:${SIZE}px;background:${color}">${GLYPH_SVG}</span>
      <span class="airtag-pin__tail" style="border-top-color:${color}"></span>
    `,
    iconSize: [SIZE, SIZE + 7],
    iconAnchor: [SIZE / 2, SIZE + 7],
    popupAnchor: [0, -(SIZE + 4)],
  })
}
