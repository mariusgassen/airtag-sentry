import { useEffect, useRef, useState } from 'react'

const MARKER_ANIMATION_MS = 300

/** Smoothly interpolates toward `target` over MARKER_ANIMATION_MS instead of
 * snapping to it - drives the same `position` prop a marker would get
 * anyway, just with intermediate React state updates, so it's fully
 * decoupled from Leaflet's own pan/zoom repositioning. (A CSS
 * transition-on-transform approach would fight that instead: Leaflet
 * re-projects markers through a different code path on every pan/zoom
 * frame, and a lingering CSS transition there reads as the marker lagging
 * behind the map rather than a deliberate move.) A no-op on mount and on any
 * jump that's already in progress being redirected - starts the ease fresh
 * from wherever the last animation actually got to, via a ref kept in sync
 * on every frame, not from a possibly-stale `target`. Used by MapCard.tsx
 * and DeviceMapCard.tsx for their selected pin's position. */
export function useAnimatedLatLng(target: [number, number]): [number, number] {
  const [displayed, setDisplayed] = useState(target)
  const displayedRef = useRef(target)
  const rafRef = useRef<number | null>(null)
  const [toLat, toLon] = target

  useEffect(() => {
    const [fromLat, fromLon] = displayedRef.current
    if (fromLat === toLat && fromLon === toLon) return
    const start = performance.now()
    function tick(now: number) {
      const t = Math.min(1, (now - start) / MARKER_ANIMATION_MS)
      const eased = 1 - (1 - t) * (1 - t)
      const next: [number, number] = [fromLat + (toLat - fromLat) * eased, fromLon + (toLon - fromLon) * eased]
      displayedRef.current = next
      setDisplayed(next)
      if (t < 1) rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
    }
  }, [toLat, toLon])

  return displayed
}
