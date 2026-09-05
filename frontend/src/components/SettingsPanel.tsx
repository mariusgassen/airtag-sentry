import { useEffect, useRef, useState } from 'react'
import type { AppSettings } from '../api'
import { getSettings, updateSettings } from '../api'
import type { ThemePreference } from '../theme'
import { useTheme } from '../theme'
import { LogoutIcon } from './icons'
import { Row, Section } from './AirtagDetail'

const THEME_OPTIONS: { value: ThemePreference; label: string }[] = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Hell' },
  { value: 'dark', label: 'Dunkel' },
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

function Field({
  label,
  suffix,
  value,
  error,
  onChange,
}: {
  label: string
  suffix: string
  value: number
  error?: string
  onChange: (v: number) => void
}) {
  return (
    <div className="border-t border-[var(--divider)] px-4 py-3 first:border-t-0">
      <div className="flex items-center justify-between gap-3">
        <span className="flex-1 text-[0.95rem]">{label}</span>
        <div className="flex shrink-0 items-center gap-1.5">
          <input
            type="number"
            min={0}
            step="any"
            value={Number.isFinite(value) ? value : ''}
            onChange={(e) => onChange(e.target.valueAsNumber)}
            className={`w-20 rounded-lg border bg-[var(--surface-2)] px-2 py-1.5 text-right text-sm outline-none focus:border-[var(--accent)] ${
              error ? 'border-[var(--destructive)]' : 'border-[var(--divider)]'
            }`}
          />
          <span className="text-sm text-[var(--text-secondary)]">{suffix}</span>
        </div>
      </div>
      {error && <p className="mt-1.5 text-right text-[0.72rem] text-[var(--destructive)]">{error}</p>}
    </div>
  )
}

type FieldKey =
  | 'polling_interval_minutes'
  | 'movement_distance_threshold_meters'
  | 'movement_stillstand_hours'
  | 'movement_stillstand_movement_meters'

const FIELD_ERROR = 'Muss größer als 0 sein.'

function validate(settings: AppSettings): Partial<Record<FieldKey, string>> {
  const errors: Partial<Record<FieldKey, string>> = {}
  const numericKeys: FieldKey[] = [
    'polling_interval_minutes',
    'movement_distance_threshold_meters',
    'movement_stillstand_hours',
    'movement_stillstand_movement_meters',
  ]
  for (const key of numericKeys) {
    const v = settings[key]
    if (!Number.isFinite(v) || v <= 0) errors[key] = FIELD_ERROR
  }
  return errors
}

export function SettingsPanel() {
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [errors, setErrors] = useState<Partial<Record<FieldKey, string>>>({})
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const debounceRef = useRef<number | null>(null)

  useEffect(() => {
    getSettings().then(setSettings)
  }, [])

  useEffect(() => {
    return () => {
      if (debounceRef.current !== null) window.clearTimeout(debounceRef.current)
    }
  }, [])

  async function persist(next: AppSettings) {
    setStatus('saving')
    try {
      const saved = await updateSettings(next)
      setSettings(saved)
      setStatus('saved')
      window.setTimeout(() => setStatus((s) => (s === 'saved' ? 'idle' : s)), 1500)
    } catch {
      setStatus('error')
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

  return (
    <div className="flex h-full flex-col overflow-y-auto pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-[calc(0.9rem+env(safe-area-inset-top))]">
      <div className="mb-4 flex items-baseline justify-between px-4">
        <h1 className="text-[1.7rem] font-bold tracking-tight">Einstellungen</h1>
        <span
          aria-live="polite"
          className={`text-[0.78rem] transition-opacity ${
            status === 'idle' ? 'opacity-0' : 'opacity-100'
          } ${status === 'error' ? 'text-[var(--destructive)]' : 'text-[var(--text-secondary)]'}`}
        >
          {status === 'saving' && 'Speichert…'}
          {status === 'saved' && 'Gespeichert'}
          {status === 'error' && 'Fehler beim Speichern'}
        </span>
      </div>

      <div className="px-3">
        <p className="mb-2 px-1 text-[0.75rem] font-medium uppercase tracking-wide text-[var(--text-secondary)]">
          Darstellung
        </p>
        <Section>
          <ThemeField />
        </Section>
      </div>

      {!settings ? (
        <p className="px-4 text-sm text-[var(--text-secondary)]">Lädt…</p>
      ) : (
        <div className="px-3">
          <p className="mb-2 px-1 text-[0.75rem] font-medium uppercase tracking-wide text-[var(--text-secondary)]">
            Abfrage
          </p>
          <Section>
            <Field
              label="Abfrageintervall"
              suffix="min"
              value={settings.polling_interval_minutes}
              error={errors.polling_interval_minutes}
              onChange={(v) => update({ polling_interval_minutes: v })}
            />
          </Section>

          <p className="mb-2 px-1 text-[0.75rem] font-medium uppercase tracking-wide text-[var(--text-secondary)]">
            Bewegungserkennung
          </p>
          <Section>
            <Field
              label="Distanzschwelle"
              suffix="m"
              value={settings.movement_distance_threshold_meters}
              error={errors.movement_distance_threshold_meters}
              onChange={(v) => update({ movement_distance_threshold_meters: v })}
            />
            <Field
              label="Stillstandsdauer"
              suffix="h"
              value={settings.movement_stillstand_hours}
              error={errors.movement_stillstand_hours}
              onChange={(v) => update({ movement_stillstand_hours: v })}
            />
            <Field
              label="Bewegung nach Stillstand"
              suffix="m"
              value={settings.movement_stillstand_movement_meters}
              error={errors.movement_stillstand_movement_meters}
              onChange={(v) => update({ movement_stillstand_movement_meters: v })}
            />
            <label className="flex items-center justify-between gap-3 border-t border-[var(--divider)] px-4 py-3">
              <span className="flex-1 text-[0.95rem]">Alarm beim ersten Abruf</span>
              <input
                type="checkbox"
                checked={settings.movement_alert_on_backfill}
                onChange={(e) => update({ movement_alert_on_backfill: e.target.checked }, { immediate: true })}
                className="h-5 w-5 accent-[var(--accent)]"
              />
            </label>
          </Section>
        </div>
      )}

      <div className="mt-auto px-3 pt-2">
        <Section>
          <Row icon={<LogoutIcon className="h-5 w-5" />} label="Abmelden" destructive onClick={() => (window.location.href = '/logout')} bordered={false} />
        </Section>
      </div>
    </div>
  )
}
