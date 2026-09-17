import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type { AppSettings, Place } from '../api'
import { getSettings, updateSettings } from '../api'
import { COLOR_PALETTE_OPTIONS } from '../airtagColor'
import type { ThemePreference } from '../theme'
import { useTheme } from '../theme'
import { BellIcon, ChevronLeftIcon, ChevronRightIcon, GearIcon, LogoutIcon, MapPinIcon, PersonIcon } from './icons'
import { Row, Section } from './AirtagDetail'
import { CartoPanel } from './CartoPanel'
import { SettingsAppleAccounts } from './SettingsAppleAccounts'
import { SettingsNotifications } from './SettingsNotifications'
import { SettingsPlaces } from './SettingsPlaces'
import type { PlaceSeed } from './SettingsPlaces'
import type { FieldKey } from './SettingsTracking'
import { SettingsTracking } from './SettingsTracking'

const THEME_OPTIONS: { value: ThemePreference; label: string }[] = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Hell' },
  { value: 'dark', label: 'Dunkel' },
]

const MAP_TILE_PROVIDER_OPTIONS: { value: AppSettings['map_tile_provider']; label: string }[] = [
  { value: 'auto', label: 'Automatisch' },
  { value: 'osm', label: 'Nur OpenStreetMap' },
]

function ThemeField() {
  const { theme, setTheme } = useTheme()
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3">
      <span className="flex-1 text-[0.95rem]">Erscheinungsbild</span>
      <div className="inline-flex shrink-0 rounded-lg bg-[var(--surface-2)] p-0.5">
        {THEME_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => setTheme(opt.value)}
            className={`rounded-md px-2.5 py-1 text-[0.78rem] ${
              theme === opt.value ? 'bg-[var(--surface)]' : 'text-[var(--text-secondary)]'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  )
}

/** Badge/pin color palette - a server-side setting (unlike ThemeField's
 * light/dark, which is a client-only preference) since it affects every
 * AirTag/device's color, shared with anyone else viewing the same dashboard. */
function PaletteField({
  value,
  onChange,
}: {
  value: AppSettings['color_palette']
  onChange: (next: AppSettings['color_palette']) => void
}) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3">
      <span className="flex-1 text-[0.95rem]">Farbpalette</span>
      <div className="inline-flex shrink-0 rounded-lg bg-[var(--surface-2)] p-0.5">
        {COLOR_PALETTE_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={`rounded-md px-2.5 py-1 text-[0.78rem] ${
              value === opt.value ? 'bg-[var(--surface)]' : 'text-[var(--text-secondary)]'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  )
}

/** Whether the map uses CARTO's styled tiles (when a key is connected in the
 * Kartenanbieter panel below) or is forced to plain OpenStreetMap regardless -
 * see mapTiles.ts's cartoTilesEnabled(). 'auto' is the default/original behavior;
 * 'osm' is an opt-out for anyone who'd rather not use the CARTO style even
 * with a key configured. */
function MapTileProviderField({
  value,
  onChange,
}: {
  value: AppSettings['map_tile_provider']
  onChange: (next: AppSettings['map_tile_provider']) => void
}) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3">
      <span className="flex-1 text-[0.95rem]">Kartenstil</span>
      <div className="inline-flex shrink-0 rounded-lg bg-[var(--surface-2)] p-0.5">
        {MAP_TILE_PROVIDER_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={`rounded-md px-2.5 py-1 text-[0.78rem] ${
              value === opt.value ? 'bg-[var(--surface)]' : 'text-[var(--text-secondary)]'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  )
}

const FIELD_ERROR = 'Muss größer als 0 sein.'

function validate(settings: AppSettings): Partial<Record<FieldKey, string>> {
  const errors: Partial<Record<FieldKey, string>> = {}
  const numericKeys: FieldKey[] = [
    'polling_interval_minutes',
    'movement_distance_threshold_meters',
    'movement_stillstand_hours',
    'movement_stillstand_movement_meters',
    'movement_away_distance_meters',
    'owner_location_max_age_minutes',
    'history_cluster_radius_meters',
  ]
  for (const key of numericKeys) {
    const v = settings[key]
    if (!Number.isFinite(v) || v <= 0) errors[key] = FIELD_ERROR
  }
  return errors
}

function BackHeader({ title, onBack, status }: { title: string; onBack: () => void; status?: ReactNode }) {
  return (
    <div className="shrink-0">
      <button
        type="button"
        onClick={onBack}
        className="flex items-center gap-0.5 px-3 pb-1 pt-[0.6rem] text-[0.95rem] text-[var(--accent)]"
      >
        <ChevronLeftIcon className="h-5 w-5" />
        Einstellungen
      </button>
      <div className="flex items-baseline justify-between px-4 pb-2">
        <h1 className="text-[1.7rem] font-bold tracking-tight">{title}</h1>
        {status}
      </div>
    </div>
  )
}

type Page = 'root' | 'notifications' | 'apple' | 'tracking' | 'places'

interface Props {
  pushStatus: 'idle' | 'active' | 'error'
  pushBusy: boolean
  onEnablePush: () => void
  onDisablePush: () => void
  onSettingsChanged: (settings: AppSettings) => void
  onCartoApiKeyChanged: (apiKey: string | null) => void
  places: Place[]
  onPlacesChanged: () => void | Promise<void>
  // A location seeded from a map popup's "Ort hier hinzufügen" - see
  // App.tsx's placeSeed/handleAddPlace.
  placeSeed?: PlaceSeed | null
  onPlaceSeedConsumed?: () => void
  // Forwarded to SettingsPlaces - see its own onRequestExpand comment.
  onRequestExpand?: () => void
  // Bumped by App.tsx's handleTabChange when the Einstellungen tab button is
  // clicked while already active - pops this panel's own page stack back to
  // 'root', mirroring the "tap the active tab to go back" behavior the
  // Objects/Zeitachse tabs get for free from their own App.tsx-level state.
  resetSignal?: number
}

export function SettingsPanel({
  pushStatus,
  pushBusy,
  onEnablePush,
  onDisablePush,
  onSettingsChanged,
  onCartoApiKeyChanged,
  places,
  onPlacesChanged,
  placeSeed = null,
  onPlaceSeedConsumed,
  onRequestExpand,
  resetSignal,
}: Props) {
  const [page, setPage] = useState<Page>('root')
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [errors, setErrors] = useState<Partial<Record<FieldKey, string>>>({})
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const debounceRef = useRef<number | null>(null)

  useEffect(() => {
    getSettings().then(setSettings)
  }, [])

  useEffect(() => {
    if (resetSignal !== undefined) setPage('root')
  }, [resetSignal])

  // A seed arriving means the user just tapped "Ort hier hinzufügen" on the
  // map (Settings isn't even necessarily open yet) - jump straight past the
  // root/Orte-list pages into the new place's editor.
  useEffect(() => {
    if (placeSeed) setPage('places')
  }, [placeSeed])

  useEffect(() => {
    return () => {
      if (debounceRef.current !== null) window.clearTimeout(debounceRef.current)
    }
  }, [])

  async function persist(next: AppSettings) {
    setSaveStatus('saving')
    try {
      const saved = await updateSettings(next)
      setSettings(saved)
      onSettingsChanged(saved)
      setSaveStatus('saved')
      window.setTimeout(() => setSaveStatus((s) => (s === 'saved' ? 'idle' : s)), 1500)
    } catch {
      setSaveStatus('error')
    }
  }

  function update(patch: Partial<AppSettings>, { immediate = false } = {}) {
    // Deriving `next` from the `settings` closure (not a setState functional
    // updater) is deliberate: the side effects below (persist, the debounce
    // timer) must run exactly once per call. A functional updater is exactly
    // what StrictMode double-invokes in dev to catch stray side effects, and
    // this one previously fired two PUTs per click as a result.
    if (!settings) return
    const next = { ...settings, ...patch }
    const nextErrors = validate(next)
    setErrors(nextErrors)
    setSettings(next)

    if (debounceRef.current !== null) {
      window.clearTimeout(debounceRef.current)
      debounceRef.current = null
    }
    if (Object.keys(nextErrors).length === 0) {
      if (immediate) {
        persist(next)
      } else {
        debounceRef.current = window.setTimeout(() => persist(next), 600)
      }
    }
  }

  if (page === 'notifications') {
    return (
      <div className="flex h-full flex-col">
        <BackHeader title="Benachrichtigungen" onBack={() => setPage('root')} />
        <div className="flex-1 overflow-y-auto pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-2">
          <SettingsNotifications
            pushStatus={pushStatus}
            pushBusy={pushBusy}
            onEnablePush={onEnablePush}
            onDisablePush={onDisablePush}
            settings={settings}
            update={update}
          />
        </div>
      </div>
    )
  }

  if (page === 'apple') {
    return (
      <div className="flex h-full flex-col">
        <BackHeader title="Apple-Konten" onBack={() => setPage('root')} />
        <div className="flex-1 overflow-y-auto pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-2">
          <SettingsAppleAccounts />
        </div>
      </div>
    )
  }

  if (page === 'tracking') {
    return (
      <div className="flex h-full flex-col">
        <BackHeader
          title="Tracking"
          onBack={() => setPage('root')}
          status={
            <span
              aria-live="polite"
              className={`text-[0.78rem] transition-opacity ${
                saveStatus === 'idle' ? 'opacity-0' : 'opacity-100'
              } ${saveStatus === 'error' ? 'text-[var(--destructive)]' : 'text-[var(--text-secondary)]'}`}
            >
              {saveStatus === 'saving' && 'Speichert…'}
              {saveStatus === 'saved' && 'Gespeichert'}
              {saveStatus === 'error' && 'Fehler beim Speichern'}
            </span>
          }
        />
        <div className="flex-1 overflow-y-auto pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-2">
          <SettingsTracking settings={settings} errors={errors} update={update} />
        </div>
      </div>
    )
  }

  if (page === 'places') {
    return (
      <div className="flex h-full flex-col">
        <BackHeader title="Orte" onBack={() => setPage('root')} />
        <div className="flex-1 overflow-y-auto pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-2">
          <SettingsPlaces
            places={places}
            onChanged={onPlacesChanged}
            seed={placeSeed}
            onSeedConsumed={onPlaceSeedConsumed}
            onRequestExpand={onRequestExpand}
          />
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 px-4 pb-2 pt-[0.9rem]">
        <h1 className="text-[1.7rem] font-bold tracking-tight">Einstellungen</h1>
      </div>

      <div className="flex flex-1 flex-col overflow-y-auto pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-2">
        <div className="px-3">
          <p className="mb-2 px-1 text-[0.75rem] font-medium uppercase tracking-wide text-[var(--text-secondary)]">
            Darstellung
          </p>
          <Section>
            <ThemeField />
            {settings && (
              <PaletteField
                value={settings.color_palette}
                onChange={(color_palette) => update({ color_palette }, { immediate: true })}
              />
            )}
            {settings && (
              <MapTileProviderField
                value={settings.map_tile_provider}
                onChange={(map_tile_provider) => update({ map_tile_provider }, { immediate: true })}
              />
            )}
          </Section>

          <CartoPanel onApiKeyChanged={onCartoApiKeyChanged} />

          <Section>
            <Row
              icon={<BellIcon className="h-5 w-5" />}
              label="Benachrichtigungen"
              trailing={<ChevronRightIcon className="h-4 w-4 text-[var(--text-secondary)]" />}
              onClick={() => setPage('notifications')}
            />
            <Row
              icon={<PersonIcon className="h-5 w-5" />}
              label="Apple-Konten"
              trailing={<ChevronRightIcon className="h-4 w-4 text-[var(--text-secondary)]" />}
              onClick={() => setPage('apple')}
            />
            <Row
              icon={<GearIcon className="h-5 w-5" />}
              label="Tracking"
              trailing={<ChevronRightIcon className="h-4 w-4 text-[var(--text-secondary)]" />}
              onClick={() => setPage('tracking')}
            />
            <Row
              icon={<MapPinIcon className="h-5 w-5" />}
              label="Orte"
              trailing={<ChevronRightIcon className="h-4 w-4 text-[var(--text-secondary)]" />}
              onClick={() => setPage('places')}
            />
          </Section>
        </div>

        <div className="mt-auto px-3 pt-2">
          <Section>
            <Row
              icon={<LogoutIcon className="h-5 w-5" />}
              label="Abmelden"
              destructive
              onClick={() => (window.location.href = '/logout')}
              bordered={false}
            />
          </Section>
        </div>
      </div>
    </div>
  )
}
