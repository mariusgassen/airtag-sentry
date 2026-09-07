import L from 'leaflet'
import { airtagColor } from './airtagColor'
import type { DeviceIconName } from './deviceIcons'

const SIZE = 32

// Mirrors AirtagGlyph's two-concentric-circle look, inlined as a raw SVG
// string since divIcon content is plain HTML rather than React.
const GLYPH_SVG = `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
  <circle cx="12" cy="12" r="6.5" stroke="white" stroke-width="1.6"/>
  <circle cx="12" cy="12" r="2" fill="white"/>
</svg>`

// 1:1 raw-SVG mirrors of deviceIcons.tsx's React components, white-on-badge
// instead of currentColor, for the same "divIcon is plain HTML" reason as
// GLYPH_SVG above - keep both in sync when adding/removing a device icon.
const DEVICE_GLYPH_SVGS: Record<DeviceIconName, string> = {
  bike: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <circle cx="6" cy="17" r="3.2" stroke="white" stroke-width="1.8"/>
    <circle cx="18" cy="17" r="3.2" stroke="white" stroke-width="1.8"/>
    <path d="M6 17l4.5-9h3.5l4 9M8.5 8h3M11 10.5l3.5 6.5" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`,
  backpack: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <rect x="6" y="8" width="12" height="13" rx="3" stroke="white" stroke-width="1.8"/>
    <path d="M9 8V6a3 3 0 0 1 6 0v2" stroke="white" stroke-width="1.8" stroke-linecap="round"/>
    <rect x="9" y="12" width="6" height="4" rx="1" stroke="white" stroke-width="1.6"/>
    <path d="M9 21v-3M15 21v-3" stroke="white" stroke-width="1.6" stroke-linecap="round"/>
  </svg>`,
  car: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <path d="M4 16v-3.5l1.7-4.2A2 2 0 0 1 7.6 7h8.8a2 2 0 0 1 1.9 1.3L20 12.5V16" stroke="white" stroke-width="1.8" stroke-linejoin="round"/>
    <path d="M4 16h16M4 12.5h16" stroke="white" stroke-width="1.8" stroke-linecap="round"/>
    <circle cx="7.5" cy="16" r="1.6" fill="white"/>
    <circle cx="16.5" cy="16" r="1.6" fill="white"/>
  </svg>`,
  keys: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <circle cx="8" cy="15" r="4" stroke="white" stroke-width="2"/>
    <path d="M11 12l9-9m0 0v4m0-4h-4" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`,
  wallet: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <rect x="3.5" y="6.5" width="17" height="12" rx="2.5" stroke="white" stroke-width="1.8"/>
    <path d="M3.5 10h17" stroke="white" stroke-width="1.8"/>
    <circle cx="16" cy="14" r="1.5" fill="white"/>
  </svg>`,
  suitcase: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <rect x="3.5" y="8" width="17" height="12" rx="2" stroke="white" stroke-width="1.8"/>
    <path d="M9 8V6a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" stroke="white" stroke-width="1.8" stroke-linecap="round"/>
    <path d="M3.5 13h17" stroke="white" stroke-width="1.8"/>
  </svg>`,
  laptop: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <rect x="4" y="5" width="16" height="10" rx="1.5" stroke="white" stroke-width="1.8"/>
    <path d="M2.5 19h19l-1.5-3H4L2.5 19Z" stroke="white" stroke-width="1.8" stroke-linejoin="round"/>
  </svg>`,
  camera: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <rect x="3" y="7" width="18" height="12" rx="2.5" stroke="white" stroke-width="1.8"/>
    <path d="M8 7l1.5-2.5h5L16 7" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="12" cy="13" r="3.3" stroke="white" stroke-width="1.8"/>
  </svg>`,
  pet: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <circle cx="7" cy="9" r="1.5" fill="white"/>
    <circle cx="12" cy="7" r="1.5" fill="white"/>
    <circle cx="17" cy="9" r="1.5" fill="white"/>
    <path d="M12 11.5c-3.3 0-6 2.4-6 5.2 0 1.7 1.4 2.8 3 2.8.9 0 1.6-.6 3-.6s2.1.6 3 .6c1.6 0 3-1.1 3-2.8 0-2.8-2.7-5.2-6-5.2Z" fill="white"/>
  </svg>`,
  headphones: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <path d="M4 14v-2a8 8 0 0 1 16 0v2" stroke="white" stroke-width="1.8" stroke-linecap="round"/>
    <rect x="3" y="13" width="4" height="7" rx="1.5" stroke="white" stroke-width="1.8"/>
    <rect x="17" y="13" width="4" height="7" rx="1.5" stroke="white" stroke-width="1.8"/>
  </svg>`,
  book: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <path d="M12 6.5c-1.6-1.2-4-1.5-7-1v12.5c3-.5 5.4-.2 7 1 1.6-1.2 4-1.5 7-1V5.5c-3-.5-5.4-.2-7 1Z" stroke="white" stroke-width="1.7" stroke-linejoin="round"/>
    <path d="M12 6.5v12.5" stroke="white" stroke-width="1.7"/>
  </svg>`,
  box: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none">
    <path d="M3.5 8.5 12 4l8.5 4.5-8.5 4.5-8.5-4.5Z" stroke="white" stroke-width="1.7" stroke-linejoin="round"/>
    <path d="M3.5 8.5V16L12 20.5 20.5 16V8.5" stroke="white" stroke-width="1.7" stroke-linejoin="round"/>
    <path d="M12 13v7.5" stroke="white" stroke-width="1.7"/>
  </svg>`,
}

/** A colored circular badge pin for an AirTag's map marker, matching the
 * same chosen (or, if unset, hash-derived) icon/color used for its
 * list/detail avatar so an item reads as the same item on the map as it
 * does in the list. */
export function airtagPinIcon(airtag: { id: string; icon?: string | null; color?: string | null }): L.DivIcon {
  const color = airtag.color ?? airtagColor(airtag.id)
  const glyph = (airtag.icon && DEVICE_GLYPH_SVGS[airtag.icon as DeviceIconName]) || GLYPH_SVG
  return L.divIcon({
    className: 'airtag-pin',
    html: `
      <span class="airtag-pin__badge" style="width:${SIZE}px;height:${SIZE}px;background:${color}">${glyph}</span>
      <span class="airtag-pin__tail" style="border-top-color:${color}"></span>
    `,
    iconSize: [SIZE, SIZE + 7],
    iconAnchor: [SIZE / 2, SIZE + 7],
    popupAnchor: [0, -(SIZE + 4)],
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
