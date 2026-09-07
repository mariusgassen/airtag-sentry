import { useEffect, useState } from 'react'
import type { AppleLoginResult, AppleTwoFactorMethod, OwnerDevice, OwnerLocation } from '../api'
import { formatRelative } from '../format'
import { ChevronRightIcon, KeyIcon } from './icons'
import { Row, Section } from './AirtagDetail'

type Step = 'credentials' | 'select-method' | 'code'

export interface AppleConnectAdapter {
  getStatus: () => Promise<{
    connected: boolean
    selected_device_id?: string | null
    selected_device_name?: string | null
  }>
  login: (email: string, password: string) => Promise<AppleLoginResult>
  // Absent for adapters whose underlying login never offers a method choice
  // (owner tracking/pyicloud) - the wizard skips straight to the code step.
  selectMethod?: (methodIndex: number) => Promise<void>
  submitCode: (code: string) => Promise<void>
  disconnect: () => Promise<void>
  // Only present for adapters that track a location (owner tracking) - the
  // AirTag-tracking adapter has no location concept of its own.
  getLocation?: () => Promise<OwnerLocation | null>
  getHistory?: (limit?: number) => Promise<OwnerLocation[]>
  // Only present for adapters where "which device" is a meaningful, explicit
  // choice (owner tracking - an Apple ID can have several devices). When
  // present, connecting isn't considered fully done until a device is picked.
  getDevices?: () => Promise<OwnerDevice[]>
  selectDevice?: (device: OwnerDevice) => Promise<void>
}

interface Props {
  title: string
  adapter: AppleConnectAdapter
}

const METHOD_LABEL = (m: AppleTwoFactorMethod) =>
  m.kind === 'sms' ? `SMS (${m.phone_number})` : 'Vertrauenswürdiges Gerät'

export function AppleConnectPanel({ title, adapter }: Props) {
  const [connected, setConnected] = useState<boolean | null>(null)
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null)
  const [selectedDeviceName, setSelectedDeviceName] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [step, setStep] = useState<Step>('credentials')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [methods, setMethods] = useState<AppleTwoFactorMethod[]>([])
  const [code, setCode] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [location, setLocation] = useState<OwnerLocation | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [history, setHistory] = useState<OwnerLocation[] | null>(null)
  const [devicePickerOpen, setDevicePickerOpen] = useState(false)
  const [devices, setDevices] = useState<OwnerDevice[] | null>(null)
  const [deviceError, setDeviceError] = useState<string | null>(null)

  useEffect(() => {
    adapter.getStatus().then((s) => {
      setConnected(s.connected)
      setSelectedDeviceId(s.selected_device_id ?? null)
      setSelectedDeviceName(s.selected_device_name ?? null)
    })
  }, [adapter])

  useEffect(() => {
    if (connected && adapter.getLocation) {
      adapter.getLocation().then(setLocation)
    }
  }, [connected, adapter])

  // Not connected to something with a device concept, or no device selected
  // yet: connecting isn't done until one is picked, so the picker shows
  // itself rather than waiting for the user to open it.
  const showDevicePicker = Boolean(connected && adapter.getDevices && (!selectedDeviceId || devicePickerOpen))

  useEffect(() => {
    if (showDevicePicker && devices === null && adapter.getDevices) {
      adapter
        .getDevices()
        .then((d) => {
          setDeviceError(null)
          setDevices(d)
        })
        .catch((err) => setDeviceError((err as Error).message))
    }
  }, [showDevicePicker, devices, adapter])

  async function refreshStatus() {
    const s = await adapter.getStatus()
    setConnected(s.connected)
    setSelectedDeviceId(s.selected_device_id ?? null)
    setSelectedDeviceName(s.selected_device_name ?? null)
    // The device list belongs to whichever account is connected right now -
    // never reuse one fetched before a login/logout/device change.
    setDevices(null)
  }

  async function handleSelectDevice(device: OwnerDevice) {
    if (!adapter.selectDevice) return
    setDeviceError(null)
    try {
      await adapter.selectDevice(device)
      await refreshStatus()
      setDevicePickerOpen(false)
    } catch (err) {
      setDeviceError((err as Error).message)
    }
  }

  async function toggleHistory() {
    const next = !historyOpen
    setHistoryOpen(next)
    if (next && history === null && adapter.getHistory) {
      setHistory(await adapter.getHistory())
    }
  }

  function reset() {
    setStep('credentials')
    setEmail('')
    setPassword('')
    setMethods([])
    setCode('')
    setError(null)
  }

  async function handleLogin() {
    if (!email.trim() || !password) {
      setError('Bitte Apple-ID und Passwort eingeben.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const result = await adapter.login(email.trim(), password)
      if (!result.requires_2fa) {
        await refreshStatus()
        setOpen(false)
        reset()
        return
      }
      if (adapter.selectMethod && result.methods.length > 1) {
        setMethods(result.methods)
        setStep('select-method')
      } else if (adapter.selectMethod) {
        await adapter.selectMethod(result.methods[0]?.index ?? 0)
        setStep('code')
      } else {
        setStep('code')
      }
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  async function handleSelectMethod(index: number) {
    setSaving(true)
    setError(null)
    try {
      await adapter.selectMethod!(index)
      setStep('code')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  async function handleSubmitCode() {
    if (!code.trim()) {
      setError('Bitte den Code eingeben.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await adapter.submitCode(code.trim())
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
    if (!confirm(`"${title}" wirklich trennen?`)) return
    await adapter.disconnect()
    await refreshStatus()
  }

  return (
    <Section>
      <Row
        icon={<KeyIcon className="h-5 w-5" />}
        label={title}
        trailing={
          <span className="flex items-center gap-2">
            <span className={`text-sm ${connected ? 'text-[var(--success)]' : 'text-[var(--text-secondary)]'}`}>
              {connected === null
                ? '…'
                : connected
                  ? selectedDeviceName
                    ? `Verbunden · ${selectedDeviceName}`
                    : 'Verbunden'
                  : 'Nicht verbunden'}
            </span>
            {!connected && <ChevronRightIcon className={`h-4 w-4 text-[var(--text-secondary)] transition-transform ${open ? 'rotate-90' : ''}`} />}
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

      {connected && adapter.getDevices && (
        <>
          {selectedDeviceId && (
            <Row
              label="Gerät ändern"
              trailing={
                <ChevronRightIcon className={`h-4 w-4 text-[var(--text-secondary)] transition-transform ${devicePickerOpen ? 'rotate-90' : ''}`} />
              }
              onClick={() => setDevicePickerOpen((v) => !v)}
            />
          )}
          {showDevicePicker && (
            <div className="border-t border-[var(--divider)] p-3">
              {!selectedDeviceId && (
                <p className="mb-2 text-sm text-[var(--text-secondary)]">
                  Welches Gerät bestimmt deinen Standort?
                </p>
              )}
              {devices === null ? (
                <p className="text-sm text-[var(--text-secondary)]">Lädt…</p>
              ) : devices.length === 0 ? (
                <p className="text-sm text-[var(--text-secondary)]">Keine Geräte gefunden.</p>
              ) : (
                <div className="flex flex-col gap-2">
                  {devices.map((d) => (
                    <button
                      key={d.id}
                      type="button"
                      onClick={() => handleSelectDevice(d)}
                      className={`rounded-lg border px-3 py-2 text-left text-sm hover:bg-white/5 ${
                        d.id === selectedDeviceId ? 'border-[var(--accent)]' : 'border-[var(--divider)]'
                      }`}
                    >
                      {d.name}
                    </button>
                  ))}
                </div>
              )}
              {deviceError && <p className="mt-2 text-[0.78rem] text-[var(--destructive)]">{deviceError}</p>}
            </div>
          )}
        </>
      )}

      {connected && adapter.getLocation && (
        <p className="border-t border-[var(--divider)] px-4 py-3 text-sm text-[var(--text-secondary)]">
          {location
            ? `Standort: ${location.lat.toFixed(4)}, ${location.lon.toFixed(4)} · ${formatRelative(location.recorded_at)}`
            : 'Noch kein Standort erfasst.'}
        </p>
      )}

      {connected && (
        <div className="border-t border-[var(--divider)] p-3">
          <button
            type="button"
            onClick={handleDisconnect}
            className="rounded-lg border border-[var(--destructive)] px-3 py-1.5 text-sm text-[var(--destructive)]"
          >
            Trennen
          </button>
        </div>
      )}

      {connected && adapter.getHistory && (
        <>
          <Row
            icon={<ChevronRightIcon className="h-5 w-5 rotate-90" />}
            label="Verlauf"
            trailing={
              <ChevronRightIcon className={`h-4 w-4 text-[var(--text-secondary)] transition-transform ${historyOpen ? 'rotate-90' : ''}`} />
            }
            onClick={toggleHistory}
          />
          {historyOpen && <OwnerLocationHistoryList entries={history} />}
        </>
      )}

      {open && !connected && (
        <div className="border-t border-[var(--divider)] p-3">
          {step === 'credentials' && (
            <>
              <input
                autoFocus
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Apple-ID (E-Mail)"
                className="mb-2 w-full rounded-lg border border-[var(--divider)] bg-[var(--surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
              />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Passwort"
                onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
                className="mb-2 w-full rounded-lg border border-[var(--divider)] bg-[var(--surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
              />
              <button
                type="button"
                onClick={handleLogin}
                disabled={saving}
                className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60"
              >
                Anmelden
              </button>
            </>
          )}

          {step === 'select-method' && (
            <div className="flex flex-col gap-2">
              <p className="text-sm text-[var(--text-secondary)]">Bestätigungsmethode wählen:</p>
              {methods.map((m) => (
                <button
                  key={m.index}
                  type="button"
                  onClick={() => handleSelectMethod(m.index)}
                  disabled={saving}
                  className="rounded-lg border border-[var(--divider)] px-3 py-2 text-left text-sm hover:bg-white/5 disabled:opacity-60"
                >
                  {METHOD_LABEL(m)}
                </button>
              ))}
            </div>
          )}

          {step === 'code' && (
            <>
              <input
                autoFocus
                inputMode="numeric"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="Bestätigungscode"
                onKeyDown={(e) => e.key === 'Enter' && handleSubmitCode()}
                className="mb-2 w-full rounded-lg border border-[var(--divider)] bg-[var(--surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
              />
              <button
                type="button"
                onClick={handleSubmitCode}
                disabled={saving}
                className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60"
              >
                Bestätigen
              </button>
            </>
          )}

          {error && <p className="mt-2 text-[0.78rem] text-[var(--destructive)]">{error}</p>}
        </div>
      )}
    </Section>
  )
}

function OwnerLocationHistoryList({ entries }: { entries: OwnerLocation[] | null }) {
  if (entries === null) {
    return (
      <div className="border-t border-[var(--divider)] p-4 text-center text-sm text-[var(--text-secondary)]">
        Lädt…
      </div>
    )
  }
  if (entries.length === 0) {
    return (
      <div className="border-t border-[var(--divider)] p-4 text-center text-sm text-[var(--text-secondary)]">
        Noch kein Standortverlauf vorhanden.
      </div>
    )
  }
  return (
    <div className="max-h-64 overflow-y-auto border-t border-[var(--divider)]">
      {entries.map((loc, i) => (
        <div
          key={loc.recorded_at}
          className={`flex items-center justify-between px-4 py-2 text-sm ${i > 0 ? 'border-t border-[var(--divider)]' : ''}`}
        >
          <span>{new Date(loc.recorded_at).toLocaleString()}</span>
          <span className="text-[var(--text-secondary)]">
            {loc.lat.toFixed(4)}, {loc.lon.toFixed(4)}
          </span>
        </div>
      ))}
    </div>
  )
}
