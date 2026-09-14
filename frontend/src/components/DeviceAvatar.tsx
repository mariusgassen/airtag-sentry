import { glyphColor } from '../airtagColor'
import { DEVICE_ICON_COMPONENTS, defaultDeviceIcon } from '../deviceIconRegistry'
import type { DeviceIconName } from '../deviceIcons'
import { PersonIcon } from './icons'

// Mirrors AirtagAvatar's two sizes.
const SIZES = {
  40: { badge: 'h-10 w-10', icon: 'h-5 w-5' },
  80: { badge: 'h-20 w-20', icon: 'h-9 w-9' },
} satisfies Record<number, { badge: string; icon: string }>

interface Props {
  device: { icon: string | null; color: string | null; device_type: string; name: string }
  size: keyof typeof SIZES
  className?: string
}

/** Colored circular badge for an owner device - the device counterpart to
 * AirtagAvatar.tsx. Uses the device's chosen icon/color when set; otherwise
 * falls back to a default guessed from its Apple device_type (see
 * defaultDeviceIcon), and only to the plain PersonIcon-on-accent look if
 * even that has no good match. */
export function DeviceAvatar({ device, size, className }: Props) {
  const { badge, icon } = SIZES[size]
  const color = device.color ?? 'var(--accent)'
  const iconName: DeviceIconName | null = (device.icon as DeviceIconName | null) ?? defaultDeviceIcon(device.device_type, device.name)
  const Glyph = iconName ? DEVICE_ICON_COMPONENTS[iconName] : PersonIcon
  return (
    <span
      className={`flex shrink-0 items-center justify-center rounded-full ${badge} ${className ?? ''}`}
      style={{ backgroundColor: color, color: device.color ? glyphColor() : '#ffffff' }}
    >
      <Glyph className={icon} />
    </span>
  )
}
