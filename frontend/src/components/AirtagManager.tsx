import { useCallback, useEffect, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import type { Airtag } from '../api'
import {
  createAirtag,
  deleteAirtag,
  deleteAirtagKey,
  getAirtags,
  setAirtagKeyB64,
  setAirtagKeyJson,
} from '../api'

interface Props {
  onClose: () => void
  onChanged: () => void | Promise<void>
}

export function AirtagManager({ onClose, onChanged }: Props) {
  const [airtags, setAirtags] = useState<Airtag[]>([])
  const [loading, setLoading] = useState(true)
  const [newName, setNewName] = useState('')

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      setAirtags(await getAirtags())
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    if (!newName.trim()) return
    await createAirtag(newName.trim())
    setNewName('')
    await refresh()
    await onChanged()
  }

  async function handleDelete(airtag: Airtag) {
    if (
      !confirm(
        `"${airtag.name}" wirklich löschen? Der gesamte Standortverlauf und der Schlüssel werden ebenfalls gelöscht.`,
      )
    )
      return
    await deleteAirtag(airtag.id)
    await refresh()
    await onChanged()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/60"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="max-h-[88vh] w-full max-w-xl overflow-y-auto rounded-t-2xl bg-[#161b22] p-4 pb-[calc(1.25rem+env(safe-area-inset-bottom))] shadow-2xl">
        <div className="sticky top-0 mb-3 flex items-center justify-between bg-[#161b22] pt-1">
          <h2 className="text-base font-semibold">AirTags verwalten</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Schließen"
            className="flex h-10 w-10 items-center justify-center rounded-full bg-[#1c2128]"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleCreate} className="mb-4 flex gap-2">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Name, z. B. Fahrrad"
            className="flex-1 rounded-lg border border-white/10 bg-[#0d1117] px-3 py-2 text-sm"
          />
          <button
            type="submit"
            className="rounded-lg bg-[#238636] px-3 py-2 text-sm font-medium text-white hover:bg-[#2ea043]"
          >
            Hinzufügen
          </button>
        </form>

        {loading ? (
          <p className="text-sm text-[#8b949e]">Lade…</p>
        ) : airtags.length === 0 ? (
          <p className="text-sm text-[#8b949e]">Noch kein AirTag vorhanden.</p>
        ) : (
          airtags.map((a) => (
            <AirtagRow
              key={a.id}
              airtag={a}
              onDelete={() => handleDelete(a)}
              onKeyChanged={async () => {
                await refresh()
                await onChanged()
              }}
            />
          ))
        )}

        <p className="mt-3 text-[0.72rem] text-[#8b949e]">
          Schlüssel extrahieren: <code>python -m findmy decrypt --out-dir data/keys</code> auf dem
          Mac, auf dem das AirTag eingerichtet ist. Details siehe README.
        </p>
      </div>
    </div>
  )
}

function AirtagRow({
  airtag,
  onDelete,
  onKeyChanged,
}: {
  airtag: Airtag
  onDelete: () => void
  onKeyChanged: () => void | Promise<void>
}) {
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
      await onKeyChanged()
    } catch (err) {
      alert('Speichern fehlgeschlagen: ' + (err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  async function handleRemoveKey() {
    if (!confirm(`Schlüssel für "${airtag.name}" wirklich entfernen?`)) return
    await deleteAirtagKey(airtag.id)
    await onKeyChanged()
  }

  return (
    <div className="mb-3 rounded-2xl border border-white/10 p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <strong className="text-sm">{airtag.name}</strong>
        <span
          className={`rounded-full px-2 py-0.5 text-[0.72rem] ${
            airtag.has_key ? 'bg-[#238636]/20 text-[#56d364]' : 'bg-[#9a6700]/20 text-[#d29922]'
          }`}
        >
          {airtag.has_key ? 'Schlüssel hinterlegt' : 'Kein Schlüssel'}
        </span>
      </div>

      <div className="mb-2 inline-flex rounded-lg bg-[#0d1117] p-0.5">
        <button
          type="button"
          onClick={() => setMode('b64')}
          className={`rounded-md px-2.5 py-1 text-[0.78rem] ${mode === 'b64' ? 'bg-[#161b22]' : 'text-[#8b949e]'}`}
        >
          Base64-Schlüssel
        </button>
        <button
          type="button"
          onClick={() => setMode('json')}
          className={`rounded-md px-2.5 py-1 text-[0.78rem] ${mode === 'json' ? 'bg-[#161b22]' : 'text-[#8b949e]'}`}
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
          className="w-full rounded-lg border border-white/10 bg-[#0d1117] p-2 font-mono text-[0.78rem]"
        />
      ) : (
        <label className="flex cursor-pointer items-center justify-center rounded-lg border border-dashed border-white/15 p-3 text-[0.8rem] text-[#8b949e]">
          <input type="file" accept="application/json" onChange={handleFile} className="hidden" />
          {jsonFile ? jsonFile.name : 'JSON-Datei auswählen (z. B. data/keys/bike.json)'}
        </label>
      )}

      <div className="mt-2 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="rounded-lg bg-[#238636] px-3 py-1.5 text-sm font-medium text-white hover:bg-[#2ea043] disabled:opacity-60"
        >
          Speichern
        </button>
        <button
          type="button"
          onClick={handleRemoveKey}
          disabled={!airtag.has_key}
          className="rounded-lg border border-[#da3633] px-3 py-1.5 text-sm text-[#da3633] hover:bg-[#da3633] hover:text-white disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-[#da3633]"
        >
          Schlüssel entfernen
        </button>
        <button
          type="button"
          onClick={onDelete}
          className="ml-auto rounded-lg border border-[#da3633] px-3 py-1.5 text-sm text-[#da3633] hover:bg-[#da3633] hover:text-white"
        >
          AirTag löschen
        </button>
      </div>
    </div>
  )
}
