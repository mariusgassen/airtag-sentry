import { useState } from 'react'
import type { OwnerDevice, OwnerLocation } from '../api'
import { renameOwnerDevice, setOwnerDeviceAppearance } from '../api'
import { airtagColor, PALETTE } from '../airtagColor'
import { DEVICE_ICON_COMPONENTS, DEVICE_ICON_LABELS, DEVICE_ICON_NAMES } from '../deviceIconRegistry'
import { deviceLabel, formatRelative } from '../format'
import { DeviceAvatar } from './DeviceAvatar'
import { Row, Section } from './AirtagDetail'
import { ChevronLeftIcon, ChevronRightIcon, PaletteIcon, PencilIcon, PersonIcon, StarIcon } from './icons'

interface Props {
  device: OwnerDevice
  location: OwnerLocation | null
  // Full location history, already fetched by App.tsx for the map's trail -
  // reused here rather than fetched again. null while still loading.
  history: OwnerLocation[] | null
  selectedLocationKey: string | null
  onSelectLocation: (recordedAt: string) => void
  onBack: () => void
  onChanged: () => void | Promise<void>
}

/** Device counterpart to AirtagDetail. Tracking/primary status are still
 * managed in Settings -> Eigene Geräte (which device to track at all), but
 * the device's own display name/icon/color live here, mirroring AirtagDetail's
 * Umbenennen/Symbol & Farbe sections exactly - this is the *only* place a
 * device's history renders too (moved out of Settings - see tasks/todo.md). */
export function DeviceDetail({
  device,
  location,
  history,
  selectedLocationKey,
  onSelectLocation,
  onBack,
  onChanged,
}: Props) {
  const [renameOpen, setRenameOpen] = useState(false)
  const [appearanceOpen, setAppearanceOpen] = useState(false)
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
          <DeviceAvatar device={device} size={80} className="mb-3" />
          <h2 className="flex items-center gap-1.5 text-xl font-semibold">
            {deviceLabel(device)}
            {device.is_primary && <StarIcon className="h-4 w-4 text-[var(--accent)]" filled />}
          </h2>
          {device.on_account === false ? (
            <p className="mt-1 text-sm text-[var(--destructive)]">Nicht mehr im iCloud-Account gefunden</p>
          ) : (
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              {location ? `Zuletzt gesehen ${formatRelative(location.recorded_at)}` : 'Kein Standort verfügbar'}
            </p>
          )}
        </div>

        <div className="px-3">
          <Section>
            <Row
              icon={<PencilIcon className="h-5 w-5" />}
              label="Umbenennen"
              trailing={<ChevronRightIcon className="h-4 w-4 text-[var(--text-secondary)]" />}
              onClick={() => setRenameOpen((v) => !v)}
              bordered={false}
            />
            {renameOpen && (
              <DeviceRenameForm
                device={device}
                onDone={async () => {
                  setRenameOpen(false)
                  await onChanged()
                }}
              />
            )}
          </Section>

          <Section>
            <Row
              icon={<PaletteIcon className="h-5 w-5" />}
              label="Symbol & Farbe"
              trailing={
                <ChevronRightIcon
                  className={`h-4 w-4 text-[var(--text-secondary)] transition-transform ${appearanceOpen ? 'rotate-90' : ''}`}
                />
              }
              onClick={() => setAppearanceOpen((v) => !v)}
              bordered={false}
            />
            {appearanceOpen && <DeviceAppearanceForm device={device} onDone={onChanged} />}
          </Section>

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
            {historyOpen && (
              <DeviceHistoryList
                history={history}
                selectedLocationKey={selectedLocationKey}
                onSelectLocation={onSelectLocation}
              />
            )}
          </Section>
        </div>
      </div>
    </div>
  )
}

function DeviceRenameForm({ device, onDone }: { device: OwnerDevice; onDone: () => void | Promise<void> }) {
  const [name, setName] = useState(device.display_name ?? device.name)
  const [saving, setSaving] = useState(false)

  async function save() {
    setSaving(true)
    try {
      const trimmed = name.trim()
      // Saving back the unchanged technical name is the same as resetting to
      // "automatic" - keeps a no-op edit from creating a redundant display_name.
      await renameOwnerDevice(device.id, trimmed && trimmed !== device.name ? trimmed : null)
      await onDone()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="border-t border-[var(--divider)] p-3">
      <div className="flex gap-2">
        <input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="flex-1 rounded-lg border border-[var(--divider)] bg-[var(--surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
        />
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="rounded-lg bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          Sichern
        </button>
      </div>
      <p className="mt-2 text-[0.72rem] text-[var(--text-secondary)]">Technischer Name (von Apple): {device.name}</p>
    </div>
  )
}

function DeviceAppearanceForm({ device, onDone }: { device: OwnerDevice; onDone: () => void | Promise<void> }) {
  const [saving, setSaving] = useState(false)
  const effectiveColor = device.color ?? airtagColor(device.id)

  async function pick(next: { icon?: string | null; color?: string | null }) {
    const icon = next.icon !== undefined ? next.icon : device.icon
    const color = next.color !== undefined ? next.color : device.color
    setSaving(true)
    try {
      await setOwnerDeviceAppearance(device.id, icon, color)
      await onDone()
    } finally {
      setSaving(false)
    }
  }

  const ringClass = 'ring-2 ring-[var(--accent)] ring-offset-2 ring-offset-[var(--surface)]'

  return (
    <div className="border-t border-[var(--divider)] p-3">
      <p className="mb-2 text-[0.72rem] font-medium uppercase tracking-wide text-[var(--text-secondary)]">Symbol</p>
      <div className="mb-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => pick({ icon: null })}
          disabled={saving}
          aria-label="Automatisch"
          title="Automatisch"
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-white disabled:opacity-60 ${device.icon === null ? ringClass : ''}`}
          style={{ backgroundColor: effectiveColor }}
        >
          <PersonIcon className="h-6 w-6" />
        </button>
        {DEVICE_ICON_NAMES.map((name) => {
          const Glyph = DEVICE_ICON_COMPONENTS[name]
          return (
            <button
              key={name}
              type="button"
              onClick={() => pick({ icon: name })}
              disabled={saving}
              aria-label={DEVICE_ICON_LABELS[name]}
              title={DEVICE_ICON_LABELS[name]}
              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-white disabled:opacity-60 ${device.icon === name ? ringClass : ''}`}
              style={{ backgroundColor: effectiveColor }}
            >
              <Glyph className="h-6 w-6" />
            </button>
          )
        })}
      </div>

      <p className="mb-2 text-[0.72rem] font-medium uppercase tracking-wide text-[var(--text-secondary)]">Farbe</p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => pick({ color: null })}
          disabled={saving}
          aria-label="Automatisch"
          title="Automatisch"
          className={`h-8 w-8 shrink-0 rounded-full border-2 border-dashed border-[var(--text-secondary)] disabled:opacity-60 ${device.color === null ? ringClass : ''}`}
        />
        {PALETTE.map((hex) => (
          <button
            key={hex}
            type="button"
            onClick={() => pick({ color: hex })}
            disabled={saving}
            aria-label={hex}
            title={hex}
            className={`h-8 w-8 shrink-0 rounded-full disabled:opacity-60 ${device.color === hex ? ringClass : ''}`}
            style={{ backgroundColor: hex }}
          />
        ))}
      </div>
    </div>
  )
}

function DeviceHistoryList({
  history,
  selectedLocationKey,
  onSelectLocation,
}: {
  history: OwnerLocation[] | null
  selectedLocationKey: string | null
  onSelectLocation: (recordedAt: string) => void
}) {
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
  // /api/owner-devices/history is already newest-first (unlike AirTag
  // reports, which arrive oldest-first and get reversed for display in
  // AirtagDetail's HistoryList) - no reversal needed here.
  return (
    <div className="max-h-64 overflow-y-auto border-t border-[var(--divider)]">
      {history.map((loc, i) => (
        <button
          type="button"
          key={loc.recorded_at}
          onClick={() => onSelectLocation(loc.recorded_at)}
          className={`flex w-full items-center justify-between px-4 py-2 text-left text-sm ${i > 0 ? 'border-t border-[var(--divider)]' : ''} ${
            loc.recorded_at === selectedLocationKey ? 'bg-[var(--accent)]/15' : 'hover:bg-white/5'
          }`}
        >
          <span>{new Date(loc.recorded_at).toLocaleString()}</span>
          <span className="text-[var(--text-secondary)]">
            {loc.lat.toFixed(4)}, {loc.lon.toFixed(4)}
          </span>
        </button>
      ))}
    </div>
  )
}
