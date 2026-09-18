import { useState } from 'react'
import type { LocationStay, OwnerDevice, OwnerLocation } from '../api'
import {
  playOwnerDeviceSound,
  renameOwnerDevice,
  setOwnerDeviceAppearance,
  setOwnerDeviceAwayAlertEnabled,
} from '../api'
import { airtagColor, glyphColor, PALETTE } from '../airtagColor'
import { DEVICE_ICON_COMPONENTS, DEVICE_ICON_LABELS, DEVICE_ICON_NAMES } from '../deviceIconRegistry'
import { deviceLabel, formatDeviceBattery, formatRelative, isLowBattery } from '../format'
import { DeviceAvatar } from './DeviceAvatar'
import { HistoryStepper, Row, Section, Switch } from './AirtagDetail'
import {
  BellIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ClockIcon,
  PaletteIcon,
  PencilIcon,
  PersonIcon,
  SpeakerIcon,
  StarIcon,
} from './icons'

interface Props {
  device: OwnerDevice
  location: OwnerLocation | null
  // Server-computed (see stays.py / GET /api/owner-devices/history) - only
  // its count is shown here now; the list itself lives in the Zeitachse tab
  // (see onViewTimeline) so there's one place that renders a history list,
  // not two. null while still loading (see App.tsx's `?? null`), distinct
  // from `[]` (no history yet).
  stays: LocationStay[] | null
  onBack: () => void
  onChanged: () => void | Promise<void>
  // Switches App.tsx to the Zeitachse tab, filtered to just this device (see
  // handleTimelineFilterChange) - replaces what used to be an inline,
  // collapsible history list duplicating that tab's own feed.
  onViewTimeline: () => void
  stepOlder?: (() => void) | null
  stepNewer?: (() => void) | null
  stepPosition?: { current: number; total: number } | null
}

/** Device counterpart to AirtagDetail. Tracking/primary status are still
 * managed in Settings -> Eigene Geräte (which device to track at all), but
 * the device's own display name/icon/color live here, mirroring AirtagDetail's
 * Umbenennen/Symbol & Farbe sections exactly - this is the *only* place a
 * device's history renders too (moved out of Settings - see tasks/todo.md). */
export function DeviceDetail({
  device,
  location,
  stays,
  onBack,
  onChanged,
  onViewTimeline,
  stepOlder,
  stepNewer,
  stepPosition,
}: Props) {
  const [renameOpen, setRenameOpen] = useState(false)
  const [appearanceOpen, setAppearanceOpen] = useState(false)
  const [soundState, setSoundState] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle')
  const [soundError, setSoundError] = useState<string | null>(null)
  const [awayAlertSaving, setAwayAlertSaving] = useState(false)

  async function handleAwayAlertToggle(enabled: boolean) {
    setAwayAlertSaving(true)
    try {
      await setOwnerDeviceAwayAlertEnabled(device.id, enabled)
      await onChanged()
    } finally {
      setAwayAlertSaving(false)
    }
  }

  async function handlePlaySound() {
    setSoundState('sending')
    setSoundError(null)
    try {
      await playOwnerDeviceSound(device.id)
      setSoundState('sent')
    } catch (err) {
      setSoundError((err as Error).message)
      setSoundState('error')
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-center justify-between px-3 pb-1 pt-[0.6rem]">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-0.5 text-[0.95rem] text-[var(--accent)]"
        >
          <ChevronLeftIcon className="h-5 w-5" />
          Objekte
        </button>
        <HistoryStepper stepOlder={stepOlder} stepNewer={stepNewer} stepPosition={stepPosition} />
      </div>

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
            <>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                {location ? `Zuletzt gesehen ${formatRelative(location.recorded_at)}` : 'Kein Standort verfügbar'}
              </p>
              {location?.battery_level != null && (
                <p
                  className={`mt-1 text-sm ${
                    isLowBattery(location.battery_level) ? 'text-[var(--destructive)]' : 'text-[var(--text-secondary)]'
                  }`}
                  title={
                    location.battery_reported
                      ? undefined
                      : 'Kein frischer Batteriewert beim letzten Fix - letzter bekannter Stand übernommen'
                  }
                >
                  Batterie: {formatDeviceBattery(location.battery_level, location.battery_status)}
                  {!location.battery_reported && '*'}
                </p>
              )}
            </>
          )}
        </div>

        <div className="px-3">
          <Section>
            <Row
              icon={<SpeakerIcon className="h-5 w-5" />}
              label="Ton abspielen"
              trailing={
                <span className="text-sm text-[var(--text-secondary)]">
                  {soundState === 'sending' ? 'Wird gesendet…' : soundState === 'sent' ? 'Gesendet' : ''}
                </span>
              }
              onClick={soundState === 'sending' ? undefined : handlePlaySound}
              bordered={false}
            />
            {soundState === 'error' && (
              <p className="border-t border-[var(--divider)] p-3 text-[0.78rem] text-[var(--destructive)]">
                {soundError}
              </p>
            )}
          </Section>

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
              icon={<BellIcon className="h-5 w-5" />}
              label="Alarm wenn du dich ohne es entfernst"
              trailing={
                <Switch
                  checked={device.is_primary ? false : device.away_alert_enabled}
                  onChange={handleAwayAlertToggle}
                  disabled={awayAlertSaving || device.is_primary}
                />
              }
              bordered={false}
            />
            {device.is_primary && (
              <p className="border-t border-[var(--divider)] p-3 text-[0.72rem] text-[var(--text-secondary)]">
                Dieses Gerät ist dein Referenzstandort und wird nicht mit sich selbst verglichen.
              </p>
            )}
          </Section>

          <Section>
            <Row
              icon={<ClockIcon className="h-5 w-5" />}
              label="Zeitachse"
              trailing={
                <span className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
                  {stays?.length ?? ''}
                  <ChevronRightIcon className="h-4 w-4" />
                </span>
              }
              onClick={onViewTimeline}
              bordered={false}
            />
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
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full disabled:opacity-60 ${device.icon === null ? ringClass : ''}`}
          style={{ backgroundColor: effectiveColor, color: glyphColor() }}
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
              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full disabled:opacity-60 ${device.icon === name ? ringClass : ''}`}
              style={{ backgroundColor: effectiveColor, color: glyphColor() }}
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
