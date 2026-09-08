import type { AppSettings } from '../api'
import { Section, Switch } from './AirtagDetail'

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

export type FieldKey =
  | 'polling_interval_minutes'
  | 'movement_distance_threshold_meters'
  | 'movement_stillstand_hours'
  | 'movement_stillstand_movement_meters'
  | 'movement_away_distance_meters'
  | 'owner_location_max_age_minutes'

interface Props {
  settings: AppSettings | null
  errors: Partial<Record<FieldKey, string>>
  update: (patch: Partial<AppSettings>, opts?: { immediate?: boolean }) => void
}

export function SettingsTracking({ settings, errors, update }: Props) {
  if (!settings) {
    return <p className="px-4 text-sm text-[var(--text-secondary)]">Lädt…</p>
  }

  return (
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
        <div className="flex items-center justify-between gap-3 border-t border-[var(--divider)] px-4 py-3">
          <span className="flex-1 text-[0.95rem]">Alarm beim ersten Abruf</span>
          <Switch
            checked={settings.movement_alert_on_backfill}
            onChange={(v) => update({ movement_alert_on_backfill: v }, { immediate: true })}
          />
        </div>
      </Section>

      <p className="mb-2 px-1 text-[0.75rem] font-medium uppercase tracking-wide text-[var(--text-secondary)]">
        Standort-Korrelation
      </p>
      <Section>
        <Field
          label="Abstand für „ohne dich“"
          suffix="m"
          value={settings.movement_away_distance_meters}
          error={errors.movement_away_distance_meters}
          onChange={(v) => update({ movement_away_distance_meters: v })}
        />
        <Field
          label="Max. Alter deines Standorts"
          suffix="min"
          value={settings.owner_location_max_age_minutes}
          error={errors.owner_location_max_age_minutes}
          onChange={(v) => update({ owner_location_max_age_minutes: v })}
        />
      </Section>
    </div>
  )
}
