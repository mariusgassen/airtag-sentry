import L from 'leaflet'
import { airtagColor, glyphColor } from './airtagColor'
import type { DeviceIconName } from './deviceIcons'

const SIZE = 32

// Mirrors AirtagGlyph's two-concentric-circle look, inlined as a raw SVG
// string since divIcon content is plain HTML rather than React. currentColor
// picks up the badge span's own `color` (see airtagPinIcon), which tracks
// the active palette's glyph color (glyphColor()) rather than being fixed.
const GLYPH_SVG = `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
  <circle cx="12" cy="12" r="6.5" stroke="currentColor" stroke-width="1.6"/>
  <circle cx="12" cy="12" r="2" fill="currentColor"/>
</svg>`

// One AirPod bud. Its vertical stem stays centered; the round head is only
// slightly offset to distinguish the left/right variants. Mirrors
// deviceIcons.tsx's AirpodBud; keep both in sync.
function bud(headCx: number, headCy: number, headR: number, stemY2: number, stemW: number, stemCx = headCx): string {
  const y1 = headCy + headR * 0.65
  const joinY = headCy + headR * 0.95
  return `<path d="M${headCx} ${y1}L${stemCx} ${joinY}V${stemY2}" stroke="currentColor" stroke-width="${stemW}" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="${headCx}" cy="${headCy}" r="${headR}" fill="currentColor"/>`
}
const AIRPODS_PAIR_INNER = `<g transform="translate(-5.5 0)">${bud(11.3, 7.5, 3.1, 15.5, 2.7, 12)}</g>
  <g transform="translate(5.5 0)">${bud(12.7, 7.5, 3.1, 15.5, 2.7, 12)}</g>`
const AIRPODS_RIGHT_INNER = bud(12.8, 7, 3.5, 16, 3, 12)
const AIRPODS_LEFT_INNER = bud(11.2, 7, 3.5, 16, 3, 12)

// 1:1 raw-SVG mirrors of deviceIcons.tsx's React components, currentColor
// instead of a fixed color, for the same "divIcon is plain HTML" reason as
// GLYPH_SVG above - keep both in sync when adding/removing a device icon.
const DEVICE_GLYPH_SVGS: Record<DeviceIconName, string> = {
  bike: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <circle cx="6.25" cy="17" r="3.15" stroke="currentColor" stroke-width="1.8"/>
    <circle cx="17.75" cy="17" r="3.15" stroke="currentColor" stroke-width="1.8"/>
    <path d="M6.25 17h7.5l-4.25-7.5h3.65l4.6 7.5M9.5 9.5 8 7h3M13.15 9.5l1.8-3h3.35" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`,
  backpack: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <rect x="6" y="8" width="12" height="13" rx="3" stroke="currentColor" stroke-width="1.8"/>
    <path d="M9 8V6a3 3 0 0 1 6 0v2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
    <rect x="9" y="12" width="6" height="4" rx="1" stroke="currentColor" stroke-width="1.6"/>
    <path d="M9 21v-3M15 21v-3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
  </svg>`,
  car: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <path d="M3.5 16.5v-3.8c0-.6.2-1.1.65-1.5l1.45-1.25 1.55-3.25A2.2 2.2 0 0 1 9.1 5.5h5.8a2.2 2.2 0 0 1 1.95 1.2l1.55 3.25 1.45 1.25c.45.4.65.9.65 1.5v3.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M5.6 10h12.8M3.5 16.5h17" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
    <circle cx="7.5" cy="16.5" r="2.1" fill="currentColor"/>
    <circle cx="16.5" cy="16.5" r="2.1" fill="currentColor"/>
  </svg>`,
  keys: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <circle cx="6.5" cy="12" r="3.6" stroke="currentColor" stroke-width="2"/>
    <path d="M10.1 12H20M16 12v3M19 12v2" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`,
  wallet: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <rect x="3.5" y="6.5" width="17" height="12" rx="2.5" stroke="currentColor" stroke-width="1.8"/>
    <path d="M3.5 10h17" stroke="currentColor" stroke-width="1.8"/>
    <circle cx="16" cy="14" r="1.5" fill="currentColor"/>
  </svg>`,
  suitcase: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <rect x="5" y="7.5" width="14" height="11.5" rx="2" stroke="currentColor" stroke-width="1.8"/>
    <path d="M9 7.5V6a1.2 1.2 0 0 1 1.2-1.2h3.6A1.2 1.2 0 0 1 15 6v1.5M5 12.5h14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
    <circle cx="8" cy="20.1" r="1" fill="currentColor"/>
    <circle cx="16" cy="20.1" r="1" fill="currentColor"/>
  </svg>`,
  laptop: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <rect x="4.5" y="5" width="15" height="9.5" rx="1.3" stroke="currentColor" stroke-width="1.8"/>
    <rect x="9" y="4.1" width="6" height="2.5" rx="1.1" fill="currentColor"/>
    <path d="M1.8 19.4h20.4l-2-3.6a1 1 0 0 0-.9-.5H4.7a1 1 0 0 0-.9.5L1.8 19.4Z" fill="currentColor"/>
  </svg>`,
  camera: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <rect x="3" y="7" width="18" height="12" rx="2.5" stroke="currentColor" stroke-width="1.8"/>
    <path d="M8 7l1.5-2.5h5L16 7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="12" cy="13" r="3.3" stroke="currentColor" stroke-width="1.8"/>
  </svg>`,
  pet: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <circle cx="7" cy="9" r="1.5" fill="currentColor"/>
    <circle cx="12" cy="7" r="1.5" fill="currentColor"/>
    <circle cx="17" cy="9" r="1.5" fill="currentColor"/>
    <path d="M12 11.5c-3.3 0-6 2.4-6 5.2 0 1.7 1.4 2.8 3 2.8.9 0 1.6-.6 3-.6s2.1.6 3 .6c1.6 0 3-1.1 3-2.8 0-2.8-2.7-5.2-6-5.2Z" fill="currentColor"/>
  </svg>`,
  headphones: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <path d="M4 14v-2.5a8 8 0 0 1 16 0V14" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
    <rect x="2.7" y="12.5" width="4.6" height="7.5" rx="2.1" fill="currentColor"/>
    <rect x="16.7" y="12.5" width="4.6" height="7.5" rx="2.1" fill="currentColor"/>
  </svg>`,
  book: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <path d="M12 6.5c-1.6-1.2-4-1.5-7-1v12.5c3-.5 5.4-.2 7 1 1.6-1.2 4-1.5 7-1V5.5c-3-.5-5.4-.2-7 1Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>
    <path d="M12 6.5v12.5" stroke="currentColor" stroke-width="1.7"/>
  </svg>`,
  box: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <path d="M3.5 8.5 12 4l8.5 4.5-8.5 4.5-8.5-4.5Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>
    <path d="M3.5 8.5V16L12 20.5 20.5 16V8.5" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>
    <path d="M12 13v7.5" stroke="currentColor" stroke-width="1.7"/>
  </svg>`,
  iphone: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <rect x="6.5" y="2.2" width="11" height="19.6" rx="3.2" stroke="currentColor" stroke-width="2.1"/>
    <rect x="9.7" y="4.3" width="4.6" height="1.6" rx="0.8" fill="currentColor"/>
  </svg>`,
  watch: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <rect x="7.5" y="7" width="9" height="12" rx="3" fill="currentColor"/>
    <rect x="9" y="3" width="6" height="3" rx="1.2" fill="currentColor"/>
    <rect x="9" y="18" width="6" height="3" rx="1.2" fill="currentColor"/>
    <rect x="16.3" y="11" width="1.6" height="3" rx="0.7" fill="currentColor"/>
  </svg>`,
  mac: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <rect x="3.5" y="7" width="17" height="10" rx="2.5" stroke="currentColor" stroke-width="1.8"/>
    <rect x="7" y="10.3" width="3.3" height="3.2" rx="0.65" fill="currentColor"/>
    <rect x="11.8" y="10.4" width="1.6" height="3" rx="0.45" fill="currentColor"/>
    <circle cx="16.8" cy="11.9" r="0.85" fill="currentColor"/>
  </svg>`,
  imac: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <rect x="3.5" y="4" width="17" height="12" rx="1.8" stroke="currentColor" stroke-width="1.8"/>
    <rect x="5.3" y="5.8" width="13.4" height="8.2" rx="0.7" fill="currentColor" fill-opacity="0.18"/>
    <path d="M12 16v3.4M8.3 20.4h7.4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
  </svg>`,
  airpods: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">${AIRPODS_PAIR_INNER}</svg>`,
  'airpods-right': `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">${AIRPODS_RIGHT_INNER}</svg>`,
  'airpods-left': `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">${AIRPODS_LEFT_INNER}</svg>`,
  'airpods-case': `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <rect x="4" y="6.5" width="16" height="11" rx="3.2" stroke="currentColor" stroke-width="1.8"/>
    <path d="M4 10h16" stroke="currentColor" stroke-width="1.5"/>
    <circle cx="12" cy="14" r="0.7" fill="currentColor"/>
  </svg>`,
}

/** Same chosen (or, if unset, hash-derived) color used for an AirTag/device's
 * list/detail avatar and map pin - also used for its own history trail once
 * selected, so the route on the map reads as visually "theirs" rather than a
 * generic accent blue. */
export function deviceColor(item: { id: string; color?: string | null }): string {
  return item.color ?? airtagColor(item.id)
}

/** Popup offset for an airtagPinIcon marker - far enough above the icon's
 * anchor (the badge's center) to clear the whole badge rather than
 * overlapping it. A bound `<Marker><Popup>` reads this automatically from
 * the icon's own `popupAnchor`, but a *standalone* Popup (MapCard.tsx's/
 * DeviceMapCard.tsx's SelectedPin, positioned directly rather than nested
 * in the Marker) has no icon to read it from, so it's exported here to be
 * passed explicitly as that Popup's own `offset` - without it, the popup's
 * default offset renders it low enough to cover the pin. */
export const PIN_POPUP_OFFSET: L.PointExpression = [0, -(SIZE / 2 + 4)]

/** A colored circular badge pin for an AirTag's map marker, matching the
 * same chosen (or, if unset, hash-derived) icon/color used for its
 * list/detail avatar so an item reads as the same item on the map as it
 * does in the list. Center-anchored (no pointer/tail) with a two-tone ring -
 * a white inner border plus a soft dark outer one - so it stays legible
 * against both light and dark map tiles, closer to Find My's own pin look. */
export function airtagPinIcon(airtag: { id: string; icon?: string | null; color?: string | null }): L.DivIcon {
  const color = deviceColor(airtag)
  const glyph = (airtag.icon && DEVICE_GLYPH_SVGS[airtag.icon as DeviceIconName]) || GLYPH_SVG
  return L.divIcon({
    className: 'airtag-pin',
    html: `<span class="airtag-pin__badge" style="width:${SIZE}px;height:${SIZE}px;background:${color};color:${glyphColor()}">${glyph}</span>`,
    iconSize: [SIZE, SIZE],
    iconAnchor: [SIZE / 2, SIZE / 2],
    popupAnchor: PIN_POPUP_OFFSET,
  })
}

/** "You are here" pulsing-dot marker, shared between MapCard (browser
 * geolocation fallback) and any map showing the owner's own device
 * location - deliberately distinct from airtagPinIcon's badge look. */
export const currentLocationIcon: L.DivIcon = L.divIcon({
  className: 'current-location-marker',
  html: '<span class="pulse"></span><span class="dot"></span>',
  iconSize: [20, 20],
  iconAnchor: [10, 10],
})

/** Owner location history trail color - a literal value rather than
 * `var(--accent)` since Leaflet sets it as a plain SVG `stroke` attribute,
 * not a CSS property, so a custom property wouldn't resolve there. Matches
 * the dark-theme accent (index.css) that currentLocationIcon's dot already
 * uses; dashed in Polyline usage to stay visually distinct from the
 * AirTag route's solid line despite the similar blue. */
export const OWNER_TRAIL_COLOR = '#0a84ff'
