import { afterEach, describe, expect, it, vi } from 'vitest'
import { isWithinPlace, mapsUrl } from './maps'

describe('maps helpers', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('checks named place radius containment using haversine distance', () => {
    const places = [{ lat: 52.52, lon: 13.405, radius_meters: 100 }]
    // Same coordinate is inside
    expect(isWithinPlace(52.52, 13.405, places)).toBe(true)
    // ~50m north (lat delta ~0.00045 deg) is inside
    expect(isWithinPlace(52.52045, 13.405, places)).toBe(true)
    // ~500m away is outside
    expect(isWithinPlace(52.525, 13.405, places)).toBe(false)
    expect(isWithinPlace(52.52, 13.405, [])).toBe(false)
  })

  it('picks Apple Maps URL on Apple platforms and Google Maps otherwise', () => {
    vi.stubGlobal('navigator', { userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)' })
    expect(mapsUrl(52.52, 13.405, 'Home & Garden')).toBe(
      'https://maps.apple.com/?ll=52.52,13.405&q=Home%20%26%20Garden',
    )

    vi.stubGlobal('navigator', { userAgent: 'Mozilla/5.0 (X11; Linux x86_64)' })
    expect(mapsUrl(52.52, 13.405, 'Home')).toBe('https://www.google.com/maps/search/?api=1&query=52.52,13.405')
  })
})
