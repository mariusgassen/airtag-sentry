import { airtagColor } from '../airtagColor'
import { AirtagGlyph } from './icons'

// Matches the two current call sites (AirtagList's row avatar, AirtagDetail's
// header avatar) - the icon is 60% of the badge, same ratio both had before.
const SIZES = {
  40: { badge: 'h-10 w-10', icon: 'h-6 w-6' },
  80: { badge: 'h-20 w-20', icon: 'h-12 w-12' },
} satisfies Record<number, { badge: string; icon: string }>

interface Props {
  airtagId: string
  size: keyof typeof SIZES
  className?: string
}

/** Colored circular badge for an AirTag - shared between the list row, the
 * detail header, and (via mapIcons.ts's matching color) the map pin, so the
 * same item reads as the same item everywhere. */
export function AirtagAvatar({ airtagId, size, className }: Props) {
  const { badge, icon } = SIZES[size]
  return (
    <span
      className={`flex shrink-0 items-center justify-center rounded-full text-white ${badge} ${className ?? ''}`}
      style={{ backgroundColor: airtagColor(airtagId) }}
    >
      <AirtagGlyph className={icon} />
    </span>
  )
}
