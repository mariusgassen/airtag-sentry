type IconProps = { className?: string }

/** Curated set of device-type glyphs a user can pick for an AirTag, shown as
 * the list/detail avatar's icon. `mapIcons.ts` mirrors these 1:1 as raw SVG
 * strings for the map pin (divIcon content is plain HTML, not React) - keep
 * both in sync when adding/removing an icon, and keep the name list in sync
 * with `AIRTAG_ICON_CHOICES` in `web/app.py`, which validates it server-side.
 * The registry tying these names to components/labels lives in
 * `deviceIconRegistry.ts` rather than here, so this module exports nothing
 * but components (Fast Refresh needs that split). */
export type DeviceIconName =
  | 'bike'
  | 'backpack'
  | 'car'
  | 'keys'
  | 'wallet'
  | 'suitcase'
  | 'laptop'
  | 'camera'
  | 'pet'
  | 'headphones'
  | 'book'
  | 'box'
  | 'iphone'
  | 'airpods'
  | 'airpods-left'
  | 'airpods-right'
  | 'airpods-case'
  | 'watch'
  | 'mac'
  | 'imac'

export function BikeIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <circle cx="6.25" cy="17" r="3.15" stroke="currentColor" strokeWidth={1.8} />
      <circle cx="17.75" cy="17" r="3.15" stroke="currentColor" strokeWidth={1.8} />
      <path
        d="M6.25 17h7.5l-4.25-7.5h3.65l4.6 7.5M9.5 9.5 8 7h3M13.15 9.5l1.8-3h3.35"
        stroke="currentColor"
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function BackpackIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="6" y="8" width="12" height="13" rx="3" stroke="currentColor" strokeWidth={1.8} />
      <path d="M9 8V6a3 3 0 0 1 6 0v2" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" />
      <rect x="9" y="12" width="6" height="4" rx="1" stroke="currentColor" strokeWidth={1.6} />
      <path d="M9 21v-3M15 21v-3" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" />
    </svg>
  )
}

export function CarIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <path
        d="M3.5 16.5v-3.8c0-.6.2-1.1.65-1.5l1.45-1.25 1.55-3.25A2.2 2.2 0 0 1 9.1 5.5h5.8a2.2 2.2 0 0 1 1.95 1.2l1.55 3.25 1.45 1.25c.45.4.65.9.65 1.5v3.8"
        stroke="currentColor"
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M5.6 10h12.8M3.5 16.5h17" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" />
      <circle cx="7.5" cy="16.5" r="2.1" fill="currentColor" />
      <circle cx="16.5" cy="16.5" r="2.1" fill="currentColor" />
    </svg>
  )
}

export function WalletIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="3.5" y="6.5" width="17" height="12" rx="2.5" stroke="currentColor" strokeWidth={1.8} />
      <path d="M3.5 10h17" stroke="currentColor" strokeWidth={1.8} />
      <circle cx="16" cy="14" r="1.5" fill="currentColor" />
    </svg>
  )
}

export function SuitcaseIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="5" y="7.5" width="14" height="11.5" rx="2" stroke="currentColor" strokeWidth={1.8} />
      <path d="M9 7.5V6a1.2 1.2 0 0 1 1.2-1.2h3.6A1.2 1.2 0 0 1 15 6v1.5M5 12.5h14" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" />
      <circle cx="8" cy="20.1" r="1" fill="currentColor" />
      <circle cx="16" cy="20.1" r="1" fill="currentColor" />
    </svg>
  )
}

export function LaptopIcon({ className }: IconProps) {
  // A camera notch straddling the screen's top edge is what reads as
  // "MacBook" rather than a generic laptop.
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="4.5" y="5" width="15" height="9.5" rx="1.3" stroke="currentColor" strokeWidth={1.8} />
      <rect x="9" y="4.1" width="6" height="2.5" rx="1.1" fill="currentColor" />
      <path
        d="M1.8 19.4h20.4l-2-3.6a1 1 0 0 0-.9-.5H4.7a1 1 0 0 0-.9.5L1.8 19.4Z"
        fill="currentColor"
      />
    </svg>
  )
}

export function CameraIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="3" y="7" width="18" height="12" rx="2.5" stroke="currentColor" strokeWidth={1.8} />
      <path d="M8 7l1.5-2.5h5L16 7" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="12" cy="13" r="3.3" stroke="currentColor" strokeWidth={1.8} />
    </svg>
  )
}

export function PetIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <circle cx="7" cy="9" r="1.5" fill="currentColor" />
      <circle cx="12" cy="7" r="1.5" fill="currentColor" />
      <circle cx="17" cy="9" r="1.5" fill="currentColor" />
      <path
        d="M12 11.5c-3.3 0-6 2.4-6 5.2 0 1.7 1.4 2.8 3 2.8.9 0 1.6-.6 3-.6s2.1.6 3 .6c1.6 0 3-1.1 3-2.8 0-2.8-2.7-5.2-6-5.2Z"
        fill="currentColor"
      />
    </svg>
  )
}

export function HeadphonesIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <path d="M4 14v-2.5a8 8 0 0 1 16 0V14" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" />
      <rect x="2.7" y="12.5" width="4.6" height="7.5" rx="2.1" fill="currentColor" />
      <rect x="16.7" y="12.5" width="4.6" height="7.5" rx="2.1" fill="currentColor" />
    </svg>
  )
}

export function BookIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <path
        d="M12 6.5c-1.6-1.2-4-1.5-7-1v12.5c3-.5 5.4-.2 7 1 1.6-1.2 4-1.5 7-1V5.5c-3-.5-5.4-.2-7 1Z"
        stroke="currentColor"
        strokeWidth={1.7}
        strokeLinejoin="round"
      />
      <path d="M12 6.5v12.5" stroke="currentColor" strokeWidth={1.7} />
    </svg>
  )
}

export function BoxIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <path d="M3.5 8.5 12 4l8.5 4.5-8.5 4.5-8.5-4.5Z" stroke="currentColor" strokeWidth={1.7} strokeLinejoin="round" />
      <path d="M3.5 8.5V16L12 20.5 20.5 16V8.5" stroke="currentColor" strokeWidth={1.7} strokeLinejoin="round" />
      <path d="M12 13v7.5" stroke="currentColor" strokeWidth={1.7} />
    </svg>
  )
}

export function IphoneIcon({ className }: IconProps) {
  // A bigger, clearly-shaped Dynamic Island pill (not a thin line) is what
  // reads as "iPhone" rather than a generic rounded rectangle.
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="6.5" y="2.2" width="11" height="19.6" rx="3.2" stroke="currentColor" strokeWidth={2.1} />
      <rect x="9.7" y="4.3" width="4.6" height="1.6" rx="0.8" fill="currentColor" />
    </svg>
  )
}

export function WatchIcon({ className }: IconProps) {
  // Crown a touch above the case's vertical center - centering it exactly
  // read as too central; nudged back up slightly.
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="7.5" y="7" width="9" height="12" rx="3" fill="currentColor" />
      <rect x="9" y="3" width="6" height="3" rx="1.2" fill="currentColor" />
      <rect x="9" y="18" width="6" height="3" rx="1.2" fill="currentColor" />
      <rect x="16.3" y="10.7" width="1.6" height="3" rx="0.7" fill="currentColor" />
    </svg>
  )
}

export function MacIcon({ className }: IconProps) {
  // A low, wide Mac Studio/mini/Pro box. Its small front ports and status
  // LED keep it from reading as a blank generic rectangle.
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="3.5" y="7" width="17" height="10" rx="2.5" stroke="currentColor" strokeWidth={1.8} />
      <rect x="7" y="10.3" width="3.3" height="3.2" rx="0.65" fill="currentColor" />
      <rect x="11.8" y="10.4" width="1.6" height="3" rx="0.45" fill="currentColor" />
      <circle cx="16.8" cy="11.9" r="0.85" fill="currentColor" />
    </svg>
  )
}

export function ImacIcon({ className }: IconProps) {
  // Monitor-on-a-stand - iMac, or any Mac with a built-in display.
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="3.5" y="4" width="17" height="12" rx="1.8" stroke="currentColor" strokeWidth={1.8} />
      <rect x="5.3" y="5.8" width="13.4" height="8.2" rx="0.7" fill="currentColor" fillOpacity={0.18} />
      <path d="M12 16v3.4M8.3 20.4h7.4" stroke="currentColor" strokeWidth={2} strokeLinecap="round" />
    </svg>
  )
}

/** One AirPod bud. The stem stays upright; only the round pod head is offset
 * slightly left/right, which distinguishes the two sides without moving the
 * complete glyph away from the badge's center. */
function AirpodBud({ headCx, stemCx = headCx, headCy, headR, stemY2, stemW }: {
  headCx: number
  stemCx?: number
  headCy: number
  headR: number
  stemY2: number
  stemW: number
}) {
  const y1 = headCy + headR * 0.65
  const joinY = headCy + headR * 0.95
  return (
    <>
      <path d={`M${headCx} ${y1}L${stemCx} ${joinY}V${stemY2}`} stroke="currentColor" strokeWidth={stemW} strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={headCx} cy={headCy} r={headR} fill="currentColor" />
    </>
  )
}

// Both single-pod glyphs keep their stem on the viewBox centerline. Their
// head is the only mirrored element, so neither icon is shifted as a whole.
export function AirpodsRightIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <AirpodBud headCx={12.8} stemCx={12} headCy={7} headR={3.5} stemY2={16} stemW={3} />
    </svg>
  )
}

export function AirpodsLeftIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <AirpodBud headCx={11.2} stemCx={12} headCy={7} headR={3.5} stemY2={16} stemW={3} />
    </svg>
  )
}

export function AirpodsIcon({ className }: IconProps) {
  // The paired glyph mirrors the slight head angle while keeping each stem
  // vertical, so it remains balanced around the badge center.
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <g transform="translate(-5.5 0)">
        <AirpodBud headCx={11.3} stemCx={12} headCy={7.5} headR={3.1} stemY2={15.5} stemW={2.7} />
      </g>
      <g transform="translate(5.5 0)">
        <AirpodBud headCx={12.7} stemCx={12} headCy={7.5} headR={3.1} stemY2={15.5} stemW={2.7} />
      </g>
    </svg>
  )
}

export function AirpodsCaseIcon({ className }: IconProps) {
  // Stroke-outline "container" style, matching wallet/suitcase/backpack
  // above rather than the buds' solid fill. Broader than tall (matches the
  // real case's proportions - it opens along its long top edge), with the
  // LED below the seam rather than on it.
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="4" y="6.5" width="16" height="11" rx="3.2" stroke="currentColor" strokeWidth={1.8} />
      <path d="M4 10h16" stroke="currentColor" strokeWidth={1.5} />
      <circle cx="12" cy="14" r="0.7" fill="currentColor" />
    </svg>
  )
}
