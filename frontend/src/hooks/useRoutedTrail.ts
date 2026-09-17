import { useEffect, useState } from 'react'
import { getRoute } from '../api'

// Routed geometry, keyed by the exact ordered point sequence - avoids
// re-requesting OSRM for a trail already routed earlier this session (same
// spirit as MapCard.tsx's addressCache). A cache miss on every new report is
// expected and fine; this only saves re-fetches of *unchanged* trails, e.g.
// switching tabs back to the same AirTag/device.
const routeCache = new Map<string, [number, number][] | null>()

function keyOf(points: [number, number][]): string {
  return points.map(([lat, lon]) => `${lat},${lon}`).join(';')
}

/** Road-following version of a trail's straight-line `points` (see
 * routing.py/getRoute) - falls back to `points` itself while the route is
 * loading, or if OSRM couldn't route it, so the trail always renders
 * something rather than going blank. Used by MapCard.tsx and
 * DeviceMapCard.tsx for their main trail Polyline (see CLAUDE.md's AirTag/
 * device parity constraint) - not OwnerTrails' background, off-by-default
 * trail for other devices, which stays straight-line. */
export function useRoutedTrail(points: [number, number][]): [number, number][] {
  const key = points.length > 1 ? keyOf(points) : ''
  const [routed, setRouted] = useState<[number, number][] | null>(() => (key ? (routeCache.get(key) ?? null) : null))

  useEffect(() => {
    if (!key) {
      setRouted(null)
      return
    }
    if (routeCache.has(key)) {
      setRouted(routeCache.get(key) ?? null)
      return
    }
    let cancelled = false
    setRouted(null)
    getRoute(points)
      .then((result) => {
        routeCache.set(key, result)
        if (!cancelled) setRouted(result)
      })
      .catch(() => {
        if (!cancelled) setRouted(null)
      })
    return () => {
      cancelled = true
    }
    // points itself is excluded - key is its stable identity, and re-running
    // this on every fresh-array-same-content render would defeat the cache.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  return routed ?? points
}
