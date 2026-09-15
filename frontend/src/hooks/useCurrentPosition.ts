import { useEffect, useState } from 'react'

/** Browser geolocation, requested once on mount. Used only as a fallback view
 * for a brand-new AirTag with no reports yet - never overrides real device
 * positions. */
export function useCurrentPosition() {
  const [position, setPosition] = useState<[number, number] | null>(null)

  useEffect(() => {
    if (!navigator.geolocation) return
    navigator.geolocation.getCurrentPosition(
      (pos) => setPosition([pos.coords.latitude, pos.coords.longitude]),
      () => setPosition(null),
      { enableHighAccuracy: false, timeout: 10_000 },
    )
  }, [])

  return position
}
