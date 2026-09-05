import { useEffect, useState } from 'react'
import type { AppSettings } from '../api'
import { getSettings, updateSettings } from '../api'
import type { ThemePreference } from '../theme'
import { useTheme } from '../theme'
import { Section } from './AirtagDetail'

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
  onChange,
}: {
  label: string
  suffix: string
  value: number
  onChange: (v: number) => void
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-t border-[var(--divider)] px-4 py-3 first:border-t-0">
      <span className="flex-1 text-[0.95rem]">{label}</span>
      <div className="flex shrink-0 items-center gap-1.5">
        <input
          type="number"
          min={0}
          step="any"
          value={Number.isFinite(value) ? value : ''}
          onChange={(e) => onChange(e.target.valueAsNumber)}
          className="w-20 rounded-lg border border-[var(--divider)] bg-[var(--surface-2)] px-2 py-1.5 text-right text-sm outline-none focus:border-[var(--accent)]"
        />
        <span className="text-sm text-[var(--text-secondary)]">{suffix}</span>
      </div>
    </div>
  )
}

export function SettingsPanel() {
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    getSettings().then(setSettings)
  }, [])

  function update(patch: Partial<AppSettings>) {
    setSettings((s) => (s ? { ...s, ...patch } : s))
    setSaved(false)
  }

  async function handleSave() {
    if (!settings) return
    if (
      !Number.isFinite(settings.polling_interval_minutes) ||
      settings.polling_interval_minutes <= 0 ||
      !Number.isFinite(settings.movement_distance_threshold_meters) ||
      settings.movement_distance_threshold_meters <= 0 ||
      !Number.isFinite(settings.movement_stillstand_hours) ||
      settings.movement_stillstand_hours <= 0 ||
      !Number.isFinite(settings.movement_stillstand_movement_meters) ||
      settings.movement_stillstand_movement_meters <= 0
    ) {
      alert('Bitte für alle Felder einen Wert größer als 0 angeben.')
      return
    }
    setSaving(true)
    try {
      const saved = await updateSettings(settings)
      setSettings(saved)
      setSaved(true)
    } catch (err) {
      alert('Speichern fehlgeschlagen: ' + (err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-[calc(0.9rem+env(safe-area-inset-top))]">
      <h1 className="mb-4 px-4 text-[1.7rem] font-bold tracking-tight">Einstellungen</h1>

      <div className="px-3">
        <p className="mb-2 px-1 text-[0.8rem] text-[var(--text-secondary)]">Darstellung</p>
        <Section>
          <ThemeField />
        </Section>
      </div>

      {!settings ? (
        <p className="px-4 text-sm text-[var(--text-secondary)]">Lädt…</p>
      ) : (
        <div className="px-3">
          <p className="mb-2 px-1 text-[0.8rem] text-[var(--text-secondary)]">Abfrage</p>
          <Section>
            <Field
              label="Abfrageintervall"
              suffix="min"
              value={settings.polling_interval_minutes}
              onChange={(v) => update({ polling_interval_minutes: v })}
            />
          </Section>

          <p className="mb-2 px-1 text-[0.8rem] text-[var(--text-secondary)]">Bewegungserkennung</p>
          <Section>
            <Field
              label="Distanzschwelle"
              suffix="m"
              value={settings.movement_distance_threshold_meters}
              onChange={(v) => update({ movement_distance_threshold_meters: v })}
            />
            <Field
              label="Stillstandsdauer"
              suffix="h"
              value={settings.movement_stillstand_hours}
              onChange={(v) => update({ movement_stillstand_hours: v })}
            />
            <Field
              label="Bewegung nach Stillstand"
              suffix="m"
              value={settings.movement_stillstand_movement_meters}
              onChange={(v) => update({ movement_stillstand_movement_meters: v })}
            />
            <label className="flex items-center justify-between gap-3 border-t border-[var(--divider)] px-4 py-3">
              <span className="flex-1 text-[0.95rem]">Alarm beim ersten Abruf</span>
              <input
                type="checkbox"
                checked={settings.movement_alert_on_backfill}
                onChange={(e) => update({ movement_alert_on_backfill: e.target.checked })}
                className="h-5 w-5 accent-[var(--accent)]"
              />
            </label>
          </Section>

          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="w-full rounded-lg bg-[var(--accent)] px-3 py-2.5 text-sm font-medium text-white disabled:opacity-60"
          >
            {saving ? 'Speichert…' : saved ? 'Gespeichert' : 'Speichern'}
          </button>
        </div>
      )}
    </div>
  )
}
