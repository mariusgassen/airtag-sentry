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

export function BikeIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <circle cx="6" cy="17" r="3.2" stroke="currentColor" strokeWidth={1.8} />
      <circle cx="18" cy="17" r="3.2" stroke="currentColor" strokeWidth={1.8} />
      <path
        d="M6 17l4.5-9h3.5l4 9M8.5 8h3M11 10.5l3.5 6.5"
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
        d="M4 16v-3.5l1.7-4.2A2 2 0 0 1 7.6 7h8.8a2 2 0 0 1 1.9 1.3L20 12.5V16"
        stroke="currentColor"
        strokeWidth={1.8}
        strokeLinejoin="round"
      />
      <path d="M4 16h16M4 12.5h16" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" />
      <circle cx="7.5" cy="16" r="1.6" fill="currentColor" />
      <circle cx="16.5" cy="16" r="1.6" fill="currentColor" />
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
      <rect x="3.5" y="8" width="17" height="12" rx="2" stroke="currentColor" strokeWidth={1.8} />
      <path d="M9 8V6a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" />
      <path d="M3.5 13h17" stroke="currentColor" strokeWidth={1.8} />
    </svg>
  )
}

export function LaptopIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="4" y="5" width="16" height="10" rx="1.5" stroke="currentColor" strokeWidth={1.8} />
      <path d="M2.5 19h19l-1.5-3H4L2.5 19Z" stroke="currentColor" strokeWidth={1.8} strokeLinejoin="round" />
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
      <path d="M4 14v-2a8 8 0 0 1 16 0v2" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" />
      <rect x="3" y="13" width="4" height="7" rx="1.5" stroke="currentColor" strokeWidth={1.8} />
      <rect x="17" y="13" width="4" height="7" rx="1.5" stroke="currentColor" strokeWidth={1.8} />
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
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="6.5" y="2.5" width="11" height="19" rx="2.3" stroke="currentColor" strokeWidth={1.8} />
      <path d="M10.5 5h3" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" />
      <circle cx="12" cy="18.2" r="0.9" fill="currentColor" />
    </svg>
  )
}

export function AirpodsIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <path
        d="M9 4.5c1.4 0 2.5 1.1 2.5 2.5v7.2c0 1.7-1.3 3.3-3 3.3S5.5 15.9 5.5 14.2V9"
        stroke="currentColor"
        strokeWidth={1.8}
        strokeLinecap="round"
      />
      <rect x="7.7" y="6.3" width="2.3" height="3.6" rx="1.15" fill="currentColor" />
      <path
        d="M15 4.5c-1.4 0-2.5 1.1-2.5 2.5v7.2c0 1.7 1.3 3.3 3 3.3s3-1.6 3-3.3V9"
        stroke="currentColor"
        strokeWidth={1.8}
        strokeLinecap="round"
      />
      <rect x="14" y="6.3" width="2.3" height="3.6" rx="1.15" fill="currentColor" />
    </svg>
  )
}
