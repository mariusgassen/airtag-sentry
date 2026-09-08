import { useState } from 'react'
import type { OwnerDevice, OwnerLocation } from '../api'
import { formatRelative } from '../format'
import { Row, Section } from './AirtagDetail'
import { ChevronLeftIcon, ChevronRightIcon, PersonIcon, StarIcon } from './icons'

interface Props {
  device: OwnerDevice
  location: OwnerLocation | null
  // Full location history, already fetched by App.tsx for the map's trail -
  // reused here rather than fetched again. null while still loading.
  history: OwnerLocation[] | null
  onBack: () => void
}

/** Device counterpart to AirtagDetail - deliberately smaller, since a device's
 * name/tracking/primary status are managed in Settings -> Eigene Geräte, not
 * here. This is the *only* place a device's history renders (moved out of
 * Settings - see tasks/todo.md): a header with its last-seen state and an
 * expandable "Verlauf" list, matching AirtagDetail's own history section. */
export function DeviceDetail({ device, location, history, onBack }: Props) {
  const [historyOpen, setHistoryOpen] = useState(false)

  return (
    <div className="flex h-full flex-col">
      <button
        type="button"
        onClick={onBack}
        className="flex shrink-0 items-center gap-0.5 px-3 pb-1 pt-[0.6rem] text-[0.95rem] text-[var(--accent)]"
      >
        <ChevronLeftIcon className="h-5 w-5" />
        Objekte
      </button>

      <div className="flex-1 overflow-y-auto pb-[calc(0.75rem+env(safe-area-inset-bottom))]">
        <div className="mb-6 flex flex-col items-center px-4 text-center">
          <span className="mb-3 flex h-20 w-20 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-white">
            <PersonIcon className="h-9 w-9" />
          </span>
          <h2 className="flex items-center gap-1.5 text-xl font-semibold">
            {device.name}
            {device.is_primary && <StarIcon className="h-4 w-4 text-[var(--accent)]" filled />}
          </h2>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            {location ? `Zuletzt gesehen ${formatRelative(location.recorded_at)}` : 'Kein Standort verfügbar'}
          </p>
        </div>

        <div className="px-3">
          <Section>
            <Row
              icon={<ChevronRightIcon className="h-5 w-5 rotate-90" />}
              label="Verlauf"
              trailing={
                <span className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
                  {history?.length ?? ''}
                  <ChevronRightIcon className={`h-4 w-4 transition-transform ${historyOpen ? 'rotate-90' : ''}`} />
                </span>
              }
              onClick={() => setHistoryOpen((v) => !v)}
              bordered={false}
            />
            {historyOpen && <DeviceHistoryList history={history} />}
          </Section>
        </div>
      </div>
    </div>
  )
}

function DeviceHistoryList({ history }: { history: OwnerLocation[] | null }) {
  if (history === null) {
    return (
      <div className="border-t border-[var(--divider)] p-4 text-center text-sm text-[var(--text-secondary)]">
        Lädt…
      </div>
    )
  }
  if (history.length === 0) {
    return (
      <div className="border-t border-[var(--divider)] p-4 text-center text-sm text-[var(--text-secondary)]">
        Noch kein Standortverlauf vorhanden.
      </div>
    )
  }
  const rows = [...history].reverse()
  return (
    <div className="max-h-64 overflow-y-auto border-t border-[var(--divider)]">
      {rows.map((loc, i) => (
        <div
          key={loc.recorded_at}
          className={`flex items-center justify-between px-4 py-2 text-sm ${i > 0 ? 'border-t border-[var(--divider)]' : ''}`}
        >
          <span>{new Date(loc.recorded_at).toLocaleString()}</span>
          <span className="text-[var(--text-secondary)]">
            {loc.lat.toFixed(4)}, {loc.lon.toFixed(4)}
          </span>
        </div>
      ))}
    </div>
  )
}
