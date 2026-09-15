import { useState } from 'react'
import { setGeocodeCorrection } from '../api'
import {
  capitalize,
  formatAirtagBattery,
  formatClusterRange,
  formatDeviceBattery,
  formatRelative,
} from '../format'
import { PencilIcon } from './icons'

/** One history row - shared shape for a single ping or a multi-ping stay,
 * with an inline "correct this label" affordance. Generic over ReportStay/
 * LocationStay (both carry the same {start, end, count, lat, lon, label}
 * fields, plus their own differently-shaped battery fields) so
 * AirtagDetail.tsx and DeviceDetail.tsx render identically (see CLAUDE.md's
 * parity constraint) despite their different anchor-key types. Which battery
 * formatter applies is inferred from `battery_level`'s own type - a string
 * (AirTag's qualitative full/medium/low/very_low) vs a number (a device's
 * 0.0-1.0 fraction) - rather than a separate "kind" prop. */
export function StayRow({
  stay,
  rowRef,
  bordered,
  selected,
  onSelect,
}: {
  stay: {
    start: string
    end: string
    count: number
    lat: number
    lon: number
    label: string | null
    battery_level?: string | number | null
    battery_status?: string | null
    // Owner-device fixes can carry forward the last known battery reading
    // when this exact fix didn't report one - AirTag reports never do (see
    // tracker._battery_level), so this is always true/absent on that side.
    battery_reported?: boolean
  }
  rowRef: (el: HTMLButtonElement | null) => void
  bordered: boolean
  selected: boolean
  onSelect: () => void
}) {
  const [correcting, setCorrecting] = useState(false)
  const [correctionInput, setCorrectionInput] = useState(stay.label ?? '')
  const [saving, setSaving] = useState(false)

  async function saveCorrection() {
    const trimmed = correctionInput.trim()
    if (!trimmed) return
    setSaving(true)
    try {
      await setGeocodeCorrection(stay.lat, stay.lon, trimmed)
      setCorrecting(false)
    } finally {
      setSaving(false)
    }
  }

  if (correcting) {
    return (
      <div className={`flex items-center gap-2 px-4 py-2 text-sm ${bordered ? 'border-t border-[var(--divider)]' : ''}`}>
        <input
          autoFocus
          value={correctionInput}
          onChange={(e) => setCorrectionInput(e.target.value)}
          placeholder="Name für diesen Ort"
          className="min-w-0 flex-1 rounded-lg border border-[var(--divider)] bg-[var(--surface-2)] px-2 py-1 text-sm outline-none focus:border-[var(--accent)]"
        />
        <button type="button" onClick={saveCorrection} disabled={saving} className="text-[var(--accent)]">
          Sichern
        </button>
        <button type="button" onClick={() => setCorrecting(false)} className="text-[var(--text-secondary)]">
          Abbrechen
        </button>
      </div>
    )
  }

  const isStay = stay.count > 1
  return (
    <button
      type="button"
      ref={rowRef}
      onClick={onSelect}
      title={
        isStay
          ? `${new Date(stay.start).toLocaleString()} – ${new Date(stay.end).toLocaleString()}`
          : new Date(stay.start).toLocaleString()
      }
      className={`group flex w-full items-center justify-between px-4 py-2 text-left text-sm ${bordered ? 'border-t border-[var(--divider)]' : ''} ${
        selected ? 'bg-[var(--accent)]/15' : 'hover:bg-white/5'
      }`}
    >
      <span className="flex items-center gap-1.5">
        {isStay ? formatClusterRange(stay.start, stay.end) : capitalize(formatRelative(stay.start))}
        <span
          onClick={(e) => {
            e.stopPropagation()
            setCorrecting(true)
          }}
        >
          <PencilIcon className="h-3 w-3 shrink-0 text-[var(--text-secondary)] opacity-0 group-hover:opacity-100" />
        </span>
      </span>
      <span className="text-[var(--text-secondary)]">
        {isStay && `${stay.count}× · `}
        {stay.label ?? `${stay.lat.toFixed(4)}, ${stay.lon.toFixed(4)}`}
        {' · '}
        {typeof stay.battery_level === 'string' ? (
          formatAirtagBattery(stay.battery_level)
        ) : typeof stay.battery_level === 'number' ? (
          <span
            title={
              stay.battery_reported
                ? undefined
                : 'Kein frischer Batteriewert bei diesem Fix - letzter bekannter Stand übernommen'
            }
          >
            {formatDeviceBattery(stay.battery_level, stay.battery_status ?? null)}
            {!stay.battery_reported && '*'}
          </span>
        ) : (
          <span title="Keine Batterieangabe für diesen Zeitpunkt">keine Angabe</span>
        )}
      </span>
    </button>
  )
}
