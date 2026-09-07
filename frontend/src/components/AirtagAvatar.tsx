import { airtagColor } from '../airtagColor'
import { DEVICE_ICON_COMPONENTS } from '../deviceIconRegistry'
import type { DeviceIconName } from '../deviceIcons'
import { AirtagGlyph } from './icons'

// Matches the two current call sites (AirtagList's row avatar, AirtagDetail's
// header avatar) - the icon is 60% of the badge, same ratio both had before.
const SIZES = {
  40: { badge: 'h-10 w-10', icon: 'h-6 w-6' },
  80: { badge: 'h-20 w-20', icon: 'h-12 w-12' },
} satisfies Record<number, { badge: string; icon: string }>

interface Props {
  airtag: { id: string; icon: string | null; color: string | null }
  size: keyof typeof SIZES
  className?: string
}

/** Colored circular badge for an AirTag - shared between the list row, the
 * detail header, and (via mapIcons.ts's matching color/icon) the map pin, so
 * the same item reads as the same item everywhere. Uses the AirTag's chosen
 * icon/color when set, falling back to the derived ring glyph / hash color
 * so an uncustomized AirTag looks exactly like it always has. */
export function AirtagAvatar({ airtag, size, className }: Props) {
  const { badge, icon } = SIZES[size]
  const color = airtag.color ?? airtagColor(airtag.id)
  const Glyph = (airtag.icon && DEVICE_ICON_COMPONENTS[airtag.icon as DeviceIconName]) || AirtagGlyph
  return (
    <span
      className={`flex shrink-0 items-center justify-center rounded-full text-white ${badge} ${className ?? ''}`}
      style={{ backgroundColor: color }}
    >
      <Glyph className={icon} />
    </span>
  )
}
