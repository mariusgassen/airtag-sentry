const EARTH_RADIUS_METERS = 6_371_000

/** Great-circle distance in meters. Mirrors movement.py's haversine_distance
 * - duplicated rather than shared since this is a different runtime, but
 * keep them in sync if the formula ever changes. */
function haversineDistanceMeters(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const toRad = (d: number) => (d * Math.PI) / 180
  const phi1 = toRad(lat1)
  const phi2 = toRad(lat2)
  const dPhi = toRad(lat2 - lat1)
  const dLambda = toRad(lon2 - lon1)

  const a = Math.sin(dPhi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
  return EARTH_RADIUS_METERS * c
}

export interface Cluster<T> {
  // All points in this cluster, in the same order as the input array (so
  // "first"/"last" here means "first/last encountered", not necessarily
  // earliest/latest by time - that depends on the caller's own array
  // direction, same asymmetry as Report vs OwnerLocation elsewhere).
  points: T[]
  // The point every other point in the cluster was compared against - used
  // as the representative position for a map marker/popup.
  anchor: T
}

/**
 * Groups consecutive points that stay within `radiusMeters` of a shared
 * anchor into one Cluster - e.g. a "stay" in one spot across several polls
 * becomes a single collapsed entry instead of one row/marker per report.
 *
 * Anchor-based (not point-to-point): each point is compared to the anchor
 * that started its cluster, not to the previous point, so slow drift can't
 * chain a stay indefinitely away from where it started (same idea as
 * movement.py's stillstand-anchor walk). Direction-agnostic - only
 * neighboring array entries are ever compared, so this works the same for
 * an oldest-first array (Report) or a newest-first one (OwnerLocation).
 */
export function clusterByProximity<T>(
  points: T[],
  getLatLon: (point: T) => [number, number],
  radiusMeters: number,
): Cluster<T>[] {
  const clusters: Cluster<T>[] = []

  for (const point of points) {
    const current = clusters[clusters.length - 1]
    if (current) {
      const [aLat, aLon] = getLatLon(current.anchor)
      const [lat, lon] = getLatLon(point)
      if (haversineDistanceMeters(aLat, aLon, lat, lon) <= radiusMeters) {
        current.points.push(point)
        continue
      }
    }
    clusters.push({ points: [point], anchor: point })
  }

  return clusters
}
