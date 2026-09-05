import { useState } from 'react'
import type { ChangeEvent, ReactNode } from 'react'
import type { Airtag, Report, Status } from '../api'
import { deleteAirtag, deleteAirtagKey, renameAirtag, setAirtagKeyB64, setAirtagKeyJson } from '../api'
import { formatRelative } from '../format'
import {
  AirtagGlyph,
  BellIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  KeyIcon,
  PencilIcon,
  TrashIcon,
} from './icons'

interface Props {
  airtag: Airtag
  status: Status | null
  reports: Report[]
  onBack: () => void
  onChanged: () => void | Promise<void>
  onDeleted: () => void | Promise<void>
  pushStatus: 'idle' | 'active' | 'error'
  onEnablePush: () => void
}

function Section({ children }: { children: ReactNode }) {
  return <div className="mb-6 overflow-hidden rounded-2xl bg-[var(--surface)]">{children}</div>
}

function Row({
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

export function AirtagDetail({ airtag, status, reports, onBack, onChanged, onDeleted, pushStatus, onEnablePush }: Props) {
  const [keyOpen, setKeyOpen] = useState(false)
  const [renameOpen, setRenameOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)

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
    <div className="flex h-full flex-col overflow-y-auto pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-[calc(0.6rem+env(safe-area-inset-top))]">
      <button
        type="button"
        onClick={onBack}
        className="mb-2 flex items-center gap-0.5 px-3 py-1 text-[0.95rem] text-[var(--accent)]"
      >
        <ChevronLeftIcon className="h-5 w-5" />
        AirTags
      </button>

      <div className="mb-6 flex flex-col items-center px-4 text-center">
        <span className="mb-3 flex h-20 w-20 items-center justify-center rounded-full bg-[var(--surface-2)] text-[var(--accent)]">
          <AirtagGlyph className="h-12 w-12" />
        </span>
        <h2 className="text-xl font-semibold">{airtag.name}</h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          {status?.last_report ? `Zuletzt gesehen ${formatRelative(status.last_report.timestamp)}` : 'Kein Standort verfügbar'}
        </p>
        {status?.last_alert && (
          <p className="mt-1 text-sm text-[var(--destructive)]">
            Alarm: {status.last_alert.reason} · {formatRelative(status.last_alert.timestamp)}
          </p>
        )}
      </div>

      <div className="px-3">
        <Section>
          <Row
            icon={<BellIcon className="h-5 w-5" filled={pushStatus === 'active'} />}
            label="Benachrichtigungen"
            trailing={
              <span className={`text-sm ${pushStatus === 'active' ? 'text-[var(--success)]' : 'text-[var(--text-secondary)]'}`}>
                {pushStatus === 'active' ? 'Aktiv' : 'Aktivieren'}
              </span>
            }
            onClick={pushStatus === 'active' ? undefined : onEnablePush}
          />
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
                {reports.length}
                <ChevronRightIcon className={`h-4 w-4 transition-transform ${historyOpen ? 'rotate-90' : ''}`} />
              </span>
            }
            onClick={() => setHistoryOpen((v) => !v)}
            bordered={false}
          />
          {historyOpen && <HistoryList reports={reports} />}
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

function HistoryList({ reports }: { reports: Report[] }) {
  const rows = [...reports].reverse()
  if (rows.length === 0) {
    return (
      <div className="border-t border-[var(--divider)] p-4 text-center text-sm text-[var(--text-secondary)]">
        Noch keine Reports vorhanden.
      </div>
    )
  }
  return (
    <div className="max-h-64 overflow-y-auto border-t border-[var(--divider)]">
      {rows.map((r, i) => (
        <div
          key={r.id}
          className={`flex items-center justify-between px-4 py-2 text-sm ${i > 0 ? 'border-t border-[var(--divider)]' : ''}`}
        >
          <span>{new Date(r.timestamp).toLocaleString()}</span>
          <span className="text-[var(--text-secondary)]">
            {r.lat.toFixed(4)}, {r.lon.toFixed(4)}
          </span>
        </div>
      ))}
    </div>
  )
}
