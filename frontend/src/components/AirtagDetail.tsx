import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, ReactNode } from 'react'
import type { Airtag, ReportStay, Status } from '../api'
import {
  deleteAirtag,
  deleteAirtagKey,
  renameAirtag,
  setAirtagAppearance,
  setAirtagKeyB64,
  setAirtagKeyJson,
} from '../api'
import { airtagColor, glyphColor, PALETTE } from '../airtagColor'
import { DEVICE_ICON_COMPONENTS, DEVICE_ICON_LABELS, DEVICE_ICON_NAMES } from '../deviceIconRegistry'
import { formatAirtagBattery, formatAlertReason, formatRelative, isLowBattery } from '../format'
import { AirtagAvatar } from './AirtagAvatar'
import { StayRow } from './StayRow'
import {
  AirtagGlyph,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ChevronUpIcon,
  KeyIcon,
  PaletteIcon,
  PencilIcon,
  TrashIcon,
} from './icons'

interface Props {
  airtag: Airtag
  status: Status | null
  // Server-computed (see stays.py / GET /api/reports).
  stays: ReportStay[]
  selectedReportId: number | null
  onSelectReport: (id: number) => void
  onBack: () => void
  onChanged: () => void | Promise<void>
  onDeleted: () => void | Promise<void>
  stepOlder?: (() => void) | null
  stepNewer?: (() => void) | null
  stepPosition?: { current: number; total: number } | null
}

export function Section({ children }: { children: ReactNode }) {
  return <div className="mb-6 overflow-hidden rounded-2xl bg-[var(--surface)]">{children}</div>
}

// Desktop counterpart to App.tsx's mobile title-bar stepper (that one's
// md:hidden - this is its mirror, hidden on mobile since the title bar
// already covers it there). Same older/newer callbacks, just rendered in
// the sidebar header instead, since the mobile-only top title bar doesn't
// exist in the desktop layout at all. Shared by AirtagDetail and
// DeviceDetail per CLAUDE.md's AirTag/device parity constraint.
//
// stepPosition is always "steps back from the latest fix" (1 = latest),
// counted the same way for both callers even though the underlying arrays
// order oldest/newest oppositely (reports oldest-first, owner locations
// newest-first, see CLAUDE.md) - App.tsx does that translation, this just
// renders whatever count it's given.
export function HistoryStepper({
  stepOlder,
  stepNewer,
  stepPosition,
}: {
  stepOlder?: (() => void) | null
  stepNewer?: (() => void) | null
  stepPosition?: { current: number; total: number } | null
}) {
  if (!stepOlder && !stepNewer) return null
  return (
    <div className="hidden items-center gap-1 rounded-full bg-[var(--surface-2)] p-0.5 md:flex">
      <button
        type="button"
        onClick={() => stepOlder?.()}
        disabled={!stepOlder}
        aria-label="Älterer Standort"
        title="Älterer Standort"
        className="rounded-full px-2.5 py-1 text-[var(--text)] disabled:opacity-30"
      >
        <ChevronDownIcon className="h-4 w-4" />
      </button>
      {stepPosition && (
        <span className="min-w-[3.5rem] text-center text-[0.72rem] tabular-nums text-[var(--text-secondary)]">
          {stepPosition.current} / {stepPosition.total}
        </span>
      )}
      <button
        type="button"
        onClick={() => stepNewer?.()}
        disabled={!stepNewer}
        aria-label="Neuerer Standort"
        title="Neuerer Standort"
        className="rounded-full px-2.5 py-1 text-[var(--text)] disabled:opacity-30"
      >
        <ChevronUpIcon className="h-4 w-4" />
      </button>
    </div>
  )
}

export function Switch({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative h-[1.7rem] w-[2.85rem] shrink-0 rounded-full transition-colors disabled:opacity-50 ${
        checked ? 'bg-[var(--success)]' : 'bg-[var(--surface-2)]'
      }`}
    >
      <span
        className={`absolute top-[2px] h-[1.45rem] w-[1.45rem] rounded-full bg-white shadow transition-[left] ${
          checked ? 'left-[20px]' : 'left-[2px]'
        }`}
      />
    </button>
  )
}

export function Row({
  icon,
  label,
  trailing,
  onClick,
  destructive,
  bordered = true,
}: {
  icon?: ReactNode
  label: string
  trailing?: ReactNode
  onClick?: () => void
  destructive?: boolean
  bordered?: boolean
}) {
  const Comp = onClick ? 'button' : 'div'
  return (
    <Comp
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      className={`flex w-full items-center gap-3 px-4 py-3 text-left ${bordered ? 'border-t border-[var(--divider)] first:border-t-0' : ''} ${
        onClick ? 'hover:bg-white/5' : ''
      }`}
    >
      {icon && (
        <span className={`shrink-0 ${destructive ? 'text-[var(--destructive)]' : 'text-[var(--accent)]'}`}>{icon}</span>
      )}
      <span className={`flex-1 text-[0.95rem] ${destructive ? 'text-[var(--destructive)]' : ''}`}>{label}</span>
      {trailing}
    </Comp>
  )
}

export function AirtagDetail({
  airtag,
  status,
  stays,
  selectedReportId,
  onSelectReport,
  onBack,
  onChanged,
  onDeleted,
  stepOlder,
  stepNewer,
  stepPosition,
}: Props) {
  const [keyOpen, setKeyOpen] = useState(false)
  const [renameOpen, setRenameOpen] = useState(false)
  const [appearanceOpen, setAppearanceOpen] = useState(false)
  // Open by default (not collapsed like the other sections) - history is
  // the reason most detail-view visits happen at all, so it shouldn't cost
  // an extra tap every time; each visit is a fresh mount (App.tsx swaps
  // detail views rather than keeping them alive), so this can't "stay
  // collapsed from last time" the way it might if state persisted.
  const [historyOpen, setHistoryOpen] = useState(true)

  async function handleDelete() {
    if (
      !confirm(
        `"${airtag.name}" wirklich entfernen? Der gesamte Standortverlauf und der Schlüssel werden ebenfalls gelöscht.`,
      )
    )
      return
    await deleteAirtag(airtag.id)
    await onDeleted()
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
          AirTags
        </button>
        <HistoryStepper stepOlder={stepOlder} stepNewer={stepNewer} stepPosition={stepPosition} />
      </div>

      <div className="flex-1 overflow-y-auto pb-[calc(0.75rem+env(safe-area-inset-bottom))]">
        <div className="mb-6 flex flex-col items-center px-4 text-center">
          <AirtagAvatar airtag={airtag} size={80} className="mb-3" />
          <h2 className="text-xl font-semibold">{airtag.name}</h2>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            {status?.last_report ? `Zuletzt gesehen ${formatRelative(status.last_report.timestamp)}` : 'Kein Standort verfügbar'}
          </p>
          {status?.last_report?.battery_level && (
            <p
              className={`mt-1 text-sm ${
                isLowBattery(status.last_report.battery_level) ? 'text-[var(--destructive)]' : 'text-[var(--text-secondary)]'
              }`}
            >
              Batterie: {formatAirtagBattery(status.last_report.battery_level)}
            </p>
          )}
          {status?.last_alert && (
            <p className="mt-1 text-sm text-[var(--destructive)]">
              Alarm: {formatAlertReason(status.last_alert.reason)} · {formatRelative(status.last_alert.timestamp)}
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
              <RenameForm
                airtag={airtag}
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
              trailing={<ChevronRightIcon className={`h-4 w-4 text-[var(--text-secondary)] transition-transform ${appearanceOpen ? 'rotate-90' : ''}`} />}
              onClick={() => setAppearanceOpen((v) => !v)}
              bordered={false}
            />
            {appearanceOpen && <AppearanceForm airtag={airtag} onDone={onChanged} />}
          </Section>

          <Section>
            <Row
              icon={<KeyIcon className="h-5 w-5" />}
              label="Schlüssel verwalten"
              trailing={
                <span className="flex items-center gap-2">
                  <span className={`text-sm ${airtag.has_key ? 'text-[var(--success)]' : 'text-[var(--text-secondary)]'}`}>
                    {airtag.has_key ? 'Hinterlegt' : 'Fehlt'}
                  </span>
                  <ChevronRightIcon className="h-4 w-4 text-[var(--text-secondary)]" />
                </span>
              }
              onClick={() => setKeyOpen((v) => !v)}
              bordered={false}
            />
            {keyOpen && <KeyForm airtag={airtag} onDone={onChanged} />}
          </Section>

          <Section>
            <Row
              icon={<ChevronRightIcon className="h-5 w-5 rotate-90" />}
              label="Verlauf"
              trailing={
                <span className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
                  {stays.length}
                  <ChevronRightIcon className={`h-4 w-4 transition-transform ${historyOpen ? 'rotate-90' : ''}`} />
                </span>
              }
              onClick={() => setHistoryOpen((v) => !v)}
              bordered={false}
            />
            {historyOpen && (
              <HistoryList stays={stays} selectedReportId={selectedReportId} onSelectReport={onSelectReport} />
            )}
          </Section>

          <Section>
            <Row
              icon={<TrashIcon className="h-5 w-5" />}
              label="AirTag entfernen"
              destructive
              onClick={handleDelete}
              bordered={false}
            />
          </Section>
        </div>
      </div>
    </div>
  )
}

function RenameForm({ airtag, onDone }: { airtag: Airtag; onDone: () => void | Promise<void> }) {
  const [name, setName] = useState(airtag.name)
  const [saving, setSaving] = useState(false)

  async function save() {
    if (!name.trim()) return
    setSaving(true)
    try {
      await renameAirtag(airtag.id, name.trim())
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
    </div>
  )
}

function AppearanceForm({ airtag, onDone }: { airtag: Airtag; onDone: () => void | Promise<void> }) {
  const [saving, setSaving] = useState(false)
  const effectiveColor = airtag.color ?? airtagColor(airtag.id)

  async function pick(next: { icon?: string | null; color?: string | null }) {
    const icon = next.icon !== undefined ? next.icon : airtag.icon
    const color = next.color !== undefined ? next.color : airtag.color
    setSaving(true)
    try {
      await setAirtagAppearance(airtag.id, icon, color)
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
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full disabled:opacity-60 ${airtag.icon === null ? ringClass : ''}`}
          style={{ backgroundColor: effectiveColor, color: glyphColor() }}
        >
          <AirtagGlyph className="h-6 w-6" />
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
              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full disabled:opacity-60 ${airtag.icon === name ? ringClass : ''}`}
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
          className={`h-8 w-8 shrink-0 rounded-full border-2 border-dashed border-[var(--text-secondary)] disabled:opacity-60 ${airtag.color === null ? ringClass : ''}`}
        />
        {PALETTE.map((hex) => (
          <button
            key={hex}
            type="button"
            onClick={() => pick({ color: hex })}
            disabled={saving}
            aria-label={hex}
            title={hex}
            className={`h-8 w-8 shrink-0 rounded-full disabled:opacity-60 ${airtag.color === hex ? ringClass : ''}`}
            style={{ backgroundColor: hex }}
          />
        ))}
      </div>
    </div>
  )
}

function KeyForm({ airtag, onDone }: { airtag: Airtag; onDone: () => void | Promise<void> }) {
  const [mode, setMode] = useState<'b64' | 'json'>('b64')
  const [b64, setB64] = useState('')
  const [jsonFile, setJsonFile] = useState<{ name: string; data: unknown } | null>(null)
  const [saving, setSaving] = useState(false)

  async function handleFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      setJsonFile({ name: file.name, data: JSON.parse(text) })
    } catch (err) {
      alert('Ungültige JSON-Datei: ' + (err as Error).message)
      e.target.value = ''
      setJsonFile(null)
    }
  }

  async function handleSave() {
    if (mode === 'b64' && !b64.trim()) {
      alert('Bitte einen Base64-Schlüssel einfügen.')
      return
    }
    if (mode === 'json' && !jsonFile) {
      alert('Bitte zuerst eine JSON-Datei auswählen.')
      return
    }
    setSaving(true)
    try {
      if (mode === 'b64') {
        await setAirtagKeyB64(airtag.id, b64.trim())
      } else {
        await setAirtagKeyJson(airtag.id, jsonFile!.data)
      }
      setB64('')
      setJsonFile(null)
      await onDone()
    } catch (err) {
      alert('Speichern fehlgeschlagen: ' + (err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  async function handleRemove() {
    if (!confirm(`Schlüssel für "${airtag.name}" wirklich entfernen?`)) return
    await deleteAirtagKey(airtag.id)
    await onDone()
  }

  return (
    <div className="border-t border-[var(--divider)] p-3">
      <div className="mb-2 inline-flex rounded-lg bg-[var(--surface-2)] p-0.5">
        <button
          type="button"
          onClick={() => setMode('b64')}
          className={`rounded-md px-2.5 py-1 text-[0.78rem] ${mode === 'b64' ? 'bg-[var(--surface)]' : 'text-[var(--text-secondary)]'}`}
        >
          Base64-Schlüssel
        </button>
        <button
          type="button"
          onClick={() => setMode('json')}
          className={`rounded-md px-2.5 py-1 text-[0.78rem] ${mode === 'json' ? 'bg-[var(--surface)]' : 'text-[var(--text-secondary)]'}`}
        >
          JSON-Datei
        </button>
      </div>

      {mode === 'b64' ? (
        <textarea
          value={b64}
          onChange={(e) => setB64(e.target.value)}
          placeholder="Base64-Schlüssel einfügen"
          rows={3}
          className="w-full rounded-lg border border-[var(--divider)] bg-[var(--surface-2)] p-2 font-mono text-[0.78rem] outline-none focus:border-[var(--accent)]"
        />
      ) : (
        <label className="flex cursor-pointer items-center justify-center rounded-lg border border-dashed border-[var(--divider)] p-3 text-[0.8rem] text-[var(--text-secondary)]">
          <input type="file" accept="application/json" onChange={handleFile} className="hidden" />
          {jsonFile ? jsonFile.name : 'JSON-Datei auswählen (z. B. data/keys/bike.json)'}
        </label>
      )}

      <div className="mt-2 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60"
        >
          Speichern
        </button>
        <button
          type="button"
          onClick={handleRemove}
          disabled={!airtag.has_key}
          className="rounded-lg border border-[var(--destructive)] px-3 py-1.5 text-sm text-[var(--destructive)] disabled:opacity-40"
        >
          Schlüssel entfernen
        </button>
      </div>
      <p className="mt-2 text-[0.72rem] text-[var(--text-secondary)]">
        Extrahieren: <code>python -m findmy decrypt --out-dir data/keys</code> auf dem Mac, auf dem
        das AirTag eingerichtet ist. Details siehe README.
      </p>
    </div>
  )
}

function HistoryList({
  stays,
  selectedReportId,
  onSelectReport,
}: {
  stays: ReportStay[]
  selectedReportId: number | null
  onSelectReport: (id: number) => void
}) {
  // Newest first for display - stays arrive in the same oldest-first order
  // as the underlying reports (see stays.py).
  const rows = [...stays].reverse()
  const rowRefs = useRef(new Map<number, HTMLButtonElement>())
  useEffect(() => {
    if (selectedReportId == null) return
    rowRefs.current.get(selectedReportId)?.scrollIntoView({ block: 'nearest' })
  }, [selectedReportId])

  if (rows.length === 0) {
    return (
      <div className="border-t border-[var(--divider)] p-4 text-center text-sm text-[var(--text-secondary)]">
        Noch keine Reports vorhanden.
      </div>
    )
  }
  return (
    <div className="max-h-80 overflow-y-auto border-t border-[var(--divider)]">
      {rows.map((s, i) => (
        <StayRow
          key={s.anchor_id}
          rowRef={(el) => {
            if (el) rowRefs.current.set(s.anchor_id, el)
            else rowRefs.current.delete(s.anchor_id)
          }}
          stay={s}
          bordered={i > 0}
          selected={s.anchor_id === selectedReportId}
          onSelect={() => onSelectReport(s.anchor_id)}
        />
      ))}
    </div>
  )
}
