import { useState } from 'react'
import type { FormEvent } from 'react'
import type { Airtag, Status } from '../api'
import { capitalize, formatRelative } from '../format'
import { AirtagGlyph, BellIcon, ChevronRightIcon, PlusIcon } from './icons'

interface Props {
  airtags: Airtag[]
  statuses: Record<string, Status>
  currentId: string | null
  onSelect: (id: string) => void
  onCreate: (name: string) => Promise<void>
  pushStatus: 'idle' | 'active' | 'error'
  onEnablePush: () => void
}

export function AirtagList({
  airtags,
  statuses,
  currentId,
  onSelect,
  onCreate,
  pushStatus,
  onEnablePush,
}: Props) {
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)

  async function handleAdd(e: FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setSaving(true)
    try {
      await onCreate(name.trim())
      setName('')
      setAdding(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between px-4 pb-2 pt-[0.9rem]">
        <h1 className="text-[1.7rem] font-bold tracking-tight">AirTags</h1>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onEnablePush}
            disabled={pushStatus === 'active'}
            aria-label="Benachrichtigungen aktivieren"
            title="Benachrichtigungen aktivieren"
            className="flex h-9 w-9 items-center justify-center rounded-full text-[var(--accent)] hover:bg-[var(--surface)] disabled:text-[var(--success)]"
          >
            <BellIcon className="h-5 w-5" filled={pushStatus === 'active'} />
          </button>
          <button
            type="button"
            onClick={() => setAdding((v) => !v)}
            aria-label="AirTag hinzufügen"
            title="AirTag hinzufügen"
            className="flex h-9 w-9 items-center justify-center rounded-full text-[var(--accent)] hover:bg-[var(--surface)]"
          >
            <PlusIcon className="h-5 w-5" />
          </button>
        </div>
      </div>

      {adding && (
        <form onSubmit={handleAdd} className="mx-4 mb-2 flex gap-2">
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Name, z. B. Fahrrad"
            className="flex-1 rounded-lg border border-[var(--divider)] bg-[var(--surface)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
          />
          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            Hinzufügen
          </button>
        </form>
      )}

      <div className="flex-1 overflow-y-auto px-2 pb-[calc(0.75rem+env(safe-area-inset-bottom))]">
        {airtags.length === 0 ? (
          <div className="mx-2 mt-4 rounded-2xl bg-[var(--surface)] p-6 text-center text-sm text-[var(--text-secondary)]">
            Noch keine AirTags.
            <br />
            Tippe auf <PlusIcon className="inline h-3.5 w-3.5 align-[-1px]" />, um eines hinzuzufügen.
          </div>
        ) : (
          <div className="overflow-hidden rounded-2xl bg-[var(--surface)]">
            {airtags.map((a, i) => {
              const status = statuses[a.id]
              const subtitle = status?.last_report
                ? capitalize(formatRelative(status.last_report.timestamp))
                : 'Kein Standort verfügbar'
              const selected = a.id === currentId
              return (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => onSelect(a.id)}
                  className={`flex w-full items-center gap-3 px-3 py-2.5 text-left ${
                    selected ? 'bg-[var(--accent)]/15' : 'hover:bg-white/5'
                  } ${i > 0 ? 'border-t border-[var(--divider)]' : ''}`}
                >
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[var(--surface-2)] text-[var(--accent)]">
                    <AirtagGlyph className="h-6 w-6" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[0.95rem] font-medium">{a.name}</span>
                    <span className="block truncate text-[0.8rem] text-[var(--text-secondary)]">{subtitle}</span>
                  </span>
                  <ChevronRightIcon className="h-4 w-4 shrink-0 text-[var(--text-secondary)]" />
                </button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
