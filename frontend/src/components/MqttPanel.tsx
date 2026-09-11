import { useEffect, useState } from 'react'
import { deleteMqttSettings, getMqttStatus, setMqttSettings } from '../api'
import { ChevronRightIcon, HomeAssistantIcon } from './icons'
import { Row, Section, Switch } from './AirtagDetail'

export function MqttPanel() {
  const [connected, setConnected] = useState<boolean | null>(null)
  const [host, setHost] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [hostInput, setHostInput] = useState('')
  const [portInput, setPortInput] = useState('1883')
  const [usernameInput, setUsernameInput] = useState('')
  const [passwordInput, setPasswordInput] = useState('')
  const [useTls, setUseTls] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    refreshStatus()
  }, [])

  async function refreshStatus() {
    const s = await getMqttStatus()
    setConnected(s.connected)
    setHost(s.connected ? `${s.host}:${s.port}` : null)
  }

  function reset() {
    setHostInput('')
    setPortInput('1883')
    setUsernameInput('')
    setPasswordInput('')
    setUseTls(false)
    setError(null)
  }

  async function handleSave() {
    if (!hostInput.trim()) {
      setError('Bitte einen Broker-Host eingeben.')
      return
    }
    const port = parseInt(portInput, 10)
    if (!Number.isFinite(port) || port <= 0) {
      setError('Ungültiger Port.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await setMqttSettings(hostInput.trim(), port, usernameInput.trim(), passwordInput, useTls)
      await refreshStatus()
      setOpen(false)
      reset()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  async function handleDisconnect() {
    if (!confirm('Home Assistant/MQTT wirklich trennen?')) return
    await deleteMqttSettings()
    await refreshStatus()
  }

  return (
    <Section>
      <Row
        icon={<HomeAssistantIcon className="h-5 w-5" />}
        label="Home Assistant"
        trailing={
          <span className="flex items-center gap-2">
            <span className={`text-sm ${connected ? 'text-[var(--success)]' : 'text-[var(--text-secondary)]'}`}>
              {connected === null ? '…' : connected ? `Verbunden · ${host}` : 'Nicht verbunden'}
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
          <p className="mb-3 text-[0.78rem] text-[var(--text-secondary)]">
            AirTags und Geräte werden bei jedem Poll per MQTT Discovery als device_tracker- und
            Batterie-Sensoren an Home Assistant veröffentlicht.
          </p>
          <div className="flex items-center justify-between gap-3 border-t border-[var(--divider)] pt-3">
            <span className="text-sm">Verbunden</span>
            <Switch checked onChange={handleDisconnect} />
          </div>
        </div>
      )}

      {open && !connected && (
        <div className="border-t border-[var(--divider)] p-3">
          <input
            autoFocus
            value={hostInput}
            onChange={(e) => setHostInput(e.target.value)}
            placeholder="Broker-Host (z. B. homeassistant.local)"
            className="mb-2 w-full rounded-lg border border-[var(--divider)] bg-[var(--surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
          />
          <input
            value={portInput}
            onChange={(e) => setPortInput(e.target.value)}
            placeholder="Port"
            inputMode="numeric"
            className="mb-2 w-full rounded-lg border border-[var(--divider)] bg-[var(--surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
          />
          <input
            value={usernameInput}
            onChange={(e) => setUsernameInput(e.target.value)}
            placeholder="Benutzername (optional)"
            className="mb-2 w-full rounded-lg border border-[var(--divider)] bg-[var(--surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
          />
          <input
            value={passwordInput}
            onChange={(e) => setPasswordInput(e.target.value)}
            placeholder="Passwort (optional)"
            type="password"
            onKeyDown={(e) => e.key === 'Enter' && handleSave()}
            className="mb-2 w-full rounded-lg border border-[var(--divider)] bg-[var(--surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
          />
          <div className="mb-3 flex items-center justify-between gap-3">
            <span className="text-sm">TLS</span>
            <Switch checked={useTls} onChange={setUseTls} />
          </div>
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
