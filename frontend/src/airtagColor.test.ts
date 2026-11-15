import { afterEach, describe, expect, it } from 'vitest'
import { PALETTE, airtagColor, glyphColor, setColorPalette } from './airtagColor'

describe('airtagColor helpers', () => {
  afterEach(() => {
    setColorPalette('pastel')
  })

  it('returns deterministic palette colors per object id', () => {
    const first = airtagColor('bike')
    const second = airtagColor('bike')
    expect(first).toBe(second)
    expect(PALETTE).toContain(first)
  })

  it('switches palette and paired glyph colors consistently', () => {
    setColorPalette('pastel')
    expect(glyphColor()).toBe('#2b2a33')
    const pastelChoice = airtagColor('keys')

    setColorPalette('pastel_white')
    expect(glyphColor()).toBe('#ffffff')
    expect(airtagColor('keys')).toBe(pastelChoice)

    setColorPalette('vivid')
    expect(glyphColor()).toBe('#ffffff')
    expect(PALETTE).toContain(airtagColor('keys'))
    expect(airtagColor('keys')).not.toBe(pastelChoice)
  })
})
