import { DEVICE_ICON_COMPONENTS } from '../deviceIconRegistry'
import type { DeviceIconName } from '../deviceIcons'
import { PersonIcon } from './icons'

// Mirrors AirtagAvatar's two sizes.
const SIZES = {
  40: { badge: 'h-10 w-10', icon: 'h-5 w-5' },
  80: { badge: 'h-20 w-20', icon: 'h-9 w-9' },
} satisfies Record<number, { badge: string; icon: string }>

interface Props {
  device: { icon: string | null; color: string | null }
  size: keyof typeof SIZES
  className?: string
}

/** Colored circular badge for an owner device - the device counterpart to
 * AirtagAvatar.tsx. Uses the device's chosen icon/color when set, falling
 * back to today's plain PersonIcon-on-accent look so an uncustomized device
 * looks exactly like it always has. */
export function DeviceAvatar({ device, size, className }: Props) {
  const { badge, icon } = SIZES[size]
  const color = device.color ?? 'var(--accent)'
  const Glyph = (device.icon && DEVICE_ICON_COMPONENTS[device.icon as DeviceIconName]) || PersonIcon
  return (
    <span
      className={`flex shrink-0 items-center justify-center rounded-full text-white ${badge} ${className ?? ''}`}
      style={{ backgroundColor: color }}
    >
      <Glyph className={icon} />
    </span>
  )
}
