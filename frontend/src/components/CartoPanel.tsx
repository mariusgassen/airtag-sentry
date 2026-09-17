import { useEffect, useState } from 'react'
import { deleteCartoApiKey, getCartoStatus, setCartoApiKey as saveCartoApiKey } from '../api'
import { ChevronRightIcon, KeyIcon } from './icons'
import { Row, Section, Switch } from './AirtagDetail'

interface Props {
  // Lets App.tsx's own live copy of the key (mapTiles.ts's CARTO_API_KEY)
  // pick up a connect/disconnect immediately, same as onSettingsChanged does
  // for color_palette - without this the map keeps using the old/no key
  // until the next full reload.
  onApiKeyChanged: (apiKey: string | null) => void
}

/** CARTO's basemap tiles (MapCard.tsx's AppTileLayer et al.) now require a
 * free API key - anonymous requests get a watermarked tile instead. Same
 * expand-a-form-on-click shape as TelegramPanel, but a single field. */
export function CartoPanel({ onApiKeyChanged }: Props) {
  const [connected, setConnected] = useState<boolean | null>(null)
  const [open, setOpen] = useState(false)
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getCartoStatus().then((s) => {
      setConnected(s.connected)
      onApiKeyChanged(s.api_key)
    })
    // Only ever read once on mount - handleSave/handleDisconnect below push
    // the same update straight through onApiKeyChanged themselves.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function reset() {
    setApiKeyInput('')
    setError(null)
  }

  async function handleSave() {
    if (!apiKeyInput.trim()) {
      setError('Bitte API-Key eingeben.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const s = await saveCartoApiKey(apiKeyInput.trim())
      setConnected(s.connected)
      onApiKeyChanged(s.api_key)
      setOpen(false)
      reset()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  async function handleDisconnect() {
    if (!confirm('Karten-API-Key wirklich entfernen? Die Karte zeigt danach wieder einfache OSM-Kacheln.')) return
    await deleteCartoApiKey()
    setConnected(false)
    onApiKeyChanged(null)
  }

  return (
    <Section>
      <Row
        icon={<KeyIcon className="h-5 w-5" />}
        label="Kartenanbieter (CARTO)"
        trailing={
          <span className="flex items-center gap-2">
            <span className={`text-sm ${connected ? 'text-[var(--success)]' : 'text-[var(--text-secondary)]'}`}>
              {connected === null ? '…' : connected ? 'Verbunden' : 'Kein API-Key'}
            </span>
            {!connected && (
              <ChevronRightIcon className={`h-4 w-4 text-[var(--text-secondary)] transition-transform ${open ? 'rotate-90' : ''}`} />
            )}
          </span>
        }
        onClick={
          connected
            ? undefined
            : () => {
                setOpen((v) => !v)
                reset()
              }
        }
        bordered={false}
      />

      {connected && (
        <div className="border-t border-[var(--divider)] p-3">
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm">Verbunden</span>
            <Switch checked onChange={handleDisconnect} />
          </div>
        </div>
      )}

      {open && !connected && (
        <div className="border-t border-[var(--divider)] p-3">
          <p className="mb-2 text-[0.78rem] text-[var(--text-secondary)]">
            Ohne Key zeigt die Karte einfache OpenStreetMap-Kacheln.{' '}
            <a
              href="https://carto.com/basemaps/apikey/"
              target="_blank"
              rel="noreferrer"
              className="text-[var(--accent)] underline"
            >
              Kostenlosen API-Key anfordern
            </a>
            .
          </p>
          <input
            autoFocus
            value={apiKeyInput}
            onChange={(e) => setApiKeyInput(e.target.value)}
            placeholder="CARTO API-Key"
            onKeyDown={(e) => e.key === 'Enter' && handleSave()}
            className="mb-2 w-full rounded-lg border border-[var(--divider)] bg-[var(--surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
          />
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60"
          >
            Verbinden
          </button>
          {error && <p className="mt-2 text-[0.78rem] text-[var(--destructive)]">{error}</p>}
        </div>
      )}
    </Section>
  )
}
