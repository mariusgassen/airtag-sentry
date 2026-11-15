import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  capitalize,
  deviceLabel,
  formatAirtagBattery,
  formatAlertReason,
  formatClusterRange,
  formatDayHeading,
  formatDeviceBattery,
  formatRelative,
  isLowBattery,
} from './format'

describe('format helpers', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 2, 15, 14, 0, 0))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('formats relative timestamps across seconds, minutes, hours, and days', () => {
    expect(formatRelative(new Date(2026, 2, 15, 13, 59, 45).toISOString())).toBe('gerade eben')
    expect(formatRelative(new Date(2026, 2, 15, 13, 59, 0).toISOString())).toBe('vor 1 Minute')
    expect(formatRelative(new Date(2026, 2, 15, 13, 50, 0).toISOString())).toBe('vor 10 Minuten')
    expect(formatRelative(new Date(2026, 2, 15, 13, 0, 0).toISOString())).toBe('vor 1 Stunde')
    expect(formatRelative(new Date(2026, 2, 15, 10, 0, 0).toISOString())).toBe('vor 4 Stunden')
    expect(formatRelative(new Date(2026, 2, 14, 14, 0, 0).toISOString())).toBe('vor 1 Tag')
    expect(formatRelative(new Date(2026, 2, 12, 14, 0, 0).toISOString())).toBe('vor 3 Tagen')
  })

  it('capitalizes standalone relative text', () => {
    expect(capitalize('vor 5 Minuten')).toBe('Vor 5 Minuten')
    expect(capitalize('')).toBe('')
  })

  it('formats same-day vs cross-midnight cluster ranges cleanly', () => {
    const t1 = new Date(2026, 2, 15, 9, 5).toISOString()
    const t2 = new Date(2026, 2, 15, 11, 30).toISOString()
    expect(formatClusterRange(t1, t2)).toContain('–')
    expect(formatClusterRange(t1, t2)).not.toContain('2026')

    const prevNight = new Date(2026, 2, 14, 23, 50).toISOString()
    const nextMorning = new Date(2026, 2, 15, 0, 12).toISOString()
    expect(formatClusterRange(prevNight, nextMorning)).toContain(' – ')
  })

  it('formats day headings for heute, gestern, and older dates', () => {
    expect(formatDayHeading(new Date(2026, 2, 15, 8, 0).toISOString())).toBe('Heute')
    expect(formatDayHeading(new Date(2026, 2, 14, 23, 59).toISOString())).toBe('Gestern')
    expect(formatDayHeading(new Date(2026, 2, 10, 12, 0).toISOString())).toContain('2026')
  })

  it('formats alert reasons, device labels, and battery states', () => {
    expect(formatAlertReason('left_behind')).toBe('Zurückgelassen')
    expect(formatAlertReason('unknown_code')).toBe('unknown_code')

    expect(deviceLabel({ name: 'iPhone', display_name: null })).toBe('iPhone')
    expect(deviceLabel({ name: 'iPhone', display_name: 'Mein Handy' })).toBe('Mein Handy')

    expect(formatAirtagBattery('full')).toBe('Voll')
    expect(formatAirtagBattery('custom')).toBe('custom')

    expect(isLowBattery('low')).toBe(true)
    expect(isLowBattery('very_low')).toBe(true)
    expect(isLowBattery('medium')).toBe(false)
    expect(isLowBattery(0.19)).toBe(true)
    expect(isLowBattery(0.2)).toBe(false)

    expect(formatDeviceBattery(0.846, 'Charging')).toBe('85 % (lädt)')
    expect(formatDeviceBattery(0.5, 'Unplugged')).toBe('50 %')
  })
})
