// Apple-system-style accent colors, used to give each AirTag a stable visual
// identity shared between its list/detail avatar and its map pin. Exported
// so the appearance picker (AirtagDetail.tsx) can offer the same colors as
// explicit choices, rather than only ever landing on one by chance.
export const PALETTE = [
  '#0a84ff', // blue
  '#ff9f0a', // orange
  '#32d74b', // green
  '#ff375f', // pink
  '#bf5af2', // purple
  '#64d2ff', // teal
  '#ff453a', // red
  '#5e5ce6', // indigo
]

/** Deterministic per-AirTag color: same id always maps to the same palette
 * entry, so an item's color stays put across reloads and between views. */
export function airtagColor(id: string): string {
  let hash = 0
  for (let i = 0; i < id.length; i++) {
    hash = (hash * 31 + id.charCodeAt(i)) | 0
  }
  return PALETTE[Math.abs(hash) % PALETTE.length]
}
