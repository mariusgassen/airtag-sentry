export type ColorPaletteName = 'vivid' | 'pastel' | 'pastel_white'

// Apple-system-style accent colors, used to give each AirTag/device a stable
// visual identity shared between its list/detail avatar and its map pin.
const VIVID_COLORS = [
  '#0a84ff', // blue
  '#ff9f0a', // orange
  '#32d74b', // green
  '#ff375f', // pink
  '#bf5af2', // purple
  '#64d2ff', // teal
  '#ff453a', // red
  '#5e5ce6', // indigo
]

// Same 8 hues, softened - shared by 'pastel' (dark glyph, the default) and
// 'pastel_white' (white glyph) below; only the paired glyph color differs.
const PASTEL_COLORS = [
  '#8fbff5',
  '#f7c48c',
  '#9bdfb0',
  '#f5a8be',
  '#d2b3ee',
  '#a3e6ee',
  '#f5a399',
  '#b3b6f2',
]

const GLYPH_COLORS: Record<ColorPaletteName, string> = {
  vivid: '#ffffff',
  pastel: '#2b2a33',
  pastel_white: '#ffffff',
}

// The active palette's colors - exported as a live `let` (not a function)
// so existing call sites (AirtagDetail's/DeviceDetail's swatch picker,
// airtagColor() below) keep reading a plain array, but always the current
// one: ES module imports are live bindings, so every consumer sees the
// reassignment below without needing a hook or prop of its own.
export let PALETTE = PASTEL_COLORS

/** Set from App.tsx whenever settings load or change - see its call site for
 * why this is a plain module variable rather than React context/a hook: every
 * consumer of PALETTE/airtagColor()/glyphColor() already re-renders whenever
 * App's `settings` state changes (none of them are memoized across that
 * boundary), so reassigning this synchronously during App's own render is
 * enough for every badge and pin to pick up a palette change immediately -
 * no need to thread a `palette` prop through the component tree just to reach
 * a handful of leaf color lookups. */
export function setColorPalette(name: ColorPaletteName): void {
  PALETTE = name === 'vivid' ? VIVID_COLORS : PASTEL_COLORS
  activeGlyphColor = GLYPH_COLORS[name]
}

export const COLOR_PALETTE_OPTIONS: { value: ColorPaletteName; label: string }[] = [
  { value: 'pastel', label: 'Pastell' },
  { value: 'pastel_white', label: 'Pastell (hell)' },
  { value: 'vivid', label: 'Kräftig' },
]

let activeGlyphColor = GLYPH_COLORS.pastel

/** The glyph/icon color to pair with the active palette's backgrounds -
 * white on the vivid palette, a dark ink on the pastel one (see PASTEL_COLORS
 * above). Used by AirtagAvatar/DeviceAvatar and mapIcons.ts instead of the
 * hardcoded "white" they used before this was configurable. */
export function glyphColor(): string {
  return activeGlyphColor
}

/** Deterministic per-AirTag/device color: same id always maps to the same
 * palette entry, so an item's color stays put across reloads and between
 * views (and switches palettes together with every other uncustomized item
 * when the setting changes, since it re-reads the live PALETTE above). */
export function airtagColor(id: string): string {
  let hash = 0
  for (let i = 0; i < id.length; i++) {
    hash = (hash * 31 + id.charCodeAt(i)) | 0
  }
  return PALETTE[Math.abs(hash) % PALETTE.length]
}
