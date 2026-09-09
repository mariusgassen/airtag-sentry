import { useEffect, useState } from 'react'
import type { ChangeEvent } from 'react'
import type { AppleLoginResult, AppleTwoFactorMethod } from '../api'
import { ChevronRightIcon, PersonIcon } from './icons'
import { Row, Section, Switch } from './AirtagDetail'

type Step = 'credentials' | 'select-method' | 'code'

export interface AppleConnectAdapter {
  getStatus: () => Promise<{
    connected: boolean
    // Only meaningful for the owner-tracking adapter - which of its
    // (possibly several) devices is currently primary, see
    // OwnerDevicesPanel.tsx and owner_tracking.set_device_primary().
    primary_device_id?: string | null
    primary_device_name?: string | null
    // Only meaningful for the owner-tracking adapter - the background
    // poller's most recent live-Apple-call failure (lapsed session,
    // transient network error, ...), cleared again on the next success.
    last_sync_error?: string | null
    // Only meaningful for the owner-tracking adapter - current Family Sharing
    // filter, see familySharingToggle/setFamilySharing below.
    include_family_devices?: boolean
  }>
  login: (email: string, password: string, includeFamily?: boolean) => Promise<AppleLoginResult>
  // Only present where a live-login fallback exists (AirTag tracking) - lets
  // the user upload a session file generated elsewhere (e.g. on a machine
  // with genuine Apple hardware) instead of the live SRP+2FA handshake, for
  // when that keeps failing with Apple's GSA 503 (see tasks/roadmap.md #12).
  importSession?: (sessionJson: unknown) => Promise<void>
  // Only meaningful for the owner-tracking adapter - pyicloud's underlying
  // PyiCloudService otherwise defaults to pulling Family Sharing members'
  // devices in alongside the account's own (see owner_tracking.py). Presence
  // of this flag is what shows the "shared with me" checkbox below; the
  // AirTag adapter (FindMy.py, no such concept) omits it.
  familySharingToggle?: boolean
  // Present alongside familySharingToggle - flips the filter on an already-
  // connected account (owner_tracking.set_include_family), no re-login
  // needed since it's just read fresh from Postgres on the next poll.
  setFamilySharing?: (includeFamily: boolean) => Promise<void>
  // Absent for adapters whose underlying login never offers a method choice
  // (owner tracking/pyicloud) - the wizard skips straight to the code step.
  selectMethod?: (methodIndex: number) => Promise<void>
  submitCode: (code: string) => Promise<void>
  disconnect: () => Promise<void>
}

interface Props {
  title: string
  adapter: AppleConnectAdapter
}

const METHOD_LABEL = (m: AppleTwoFactorMethod) =>
  m.kind === 'sms' ? `SMS (${m.phone_number})` : 'Vertrauenswürdiges Gerät'

export function AppleConnectPanel({ title, adapter }: Props) {
  const [connected, setConnected] = useState<boolean | null>(null)
  const [primaryDeviceName, setPrimaryDeviceName] = useState<string | null>(null)
  const [syncError, setSyncError] = useState<string | null>(null)
  const [familySharing, setFamilySharingState] = useState(false)
  const [familySharingBusy, setFamilySharingBusy] = useState(false)
  const [open, setOpen] = useState(false)
  const [step, setStep] = useState<Step>('credentials')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [includeFamily, setIncludeFamily] = useState(false)
  const [methods, setMethods] = useState<AppleTwoFactorMethod[]>([])
  const [code, setCode] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    adapter.getStatus().then((s) => {
      setConnected(s.connected)
      setPrimaryDeviceName(s.primary_device_name ?? null)
      setSyncError(s.last_sync_error ?? null)
      setFamilySharingState(s.include_family_devices ?? false)
    })
  }, [adapter])

  async function refreshStatus() {
    const s = await adapter.getStatus()
    setConnected(s.connected)
    setPrimaryDeviceName(s.primary_device_name ?? null)
    setSyncError(s.last_sync_error ?? null)
    setFamilySharingState(s.include_family_devices ?? false)
  }

  async function handleToggleFamilySharing() {
    if (!adapter.setFamilySharing) return
    setFamilySharingBusy(true)
    try {
      await adapter.setFamilySharing(!familySharing)
      await refreshStatus()
    } finally {
      setFamilySharingBusy(false)
    }
  }

  function reset() {
    setStep('credentials')
    setEmail('')
    setPassword('')
    setIncludeFamily(false)
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
      const result = await adapter.login(email.trim(), password, includeFamily)
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

  async function handleImportSession(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file || !adapter.importSession) return
    setSaving(true)
    setError(null)
    try {
      const text = await file.text()
      await adapter.importSession(JSON.parse(text))
      await refreshStatus()
      setOpen(false)
      reset()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
      e.target.value = ''
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
        icon={<PersonIcon className="h-5 w-5" />}
        label={title}
        trailing={
          <span className="flex items-center gap-2">
            <span className={`text-sm ${connected ? 'text-[var(--success)]' : 'text-[var(--text-secondary)]'}`}>
              {connected === null
                ? '…'
                : connected
                  ? primaryDeviceName
                    ? `Verbunden · ${primaryDeviceName}`
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

      {connected && (
        <div className="border-t border-[var(--divider)] p-3">
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm">Verbunden</span>
            <Switch checked onChange={handleDisconnect} />
          </div>
          {adapter.setFamilySharing && (
            <div className="mt-3 flex items-center justify-between gap-3 border-t border-[var(--divider)] pt-3">
              <span className="text-sm">Auch mit mir geteilte Geräte (Familienfreigabe)</span>
              <Switch checked={familySharing} disabled={familySharingBusy} onChange={handleToggleFamilySharing} />
            </div>
          )}
          {syncError && (
            <p className="mt-2 text-[0.78rem] text-[var(--destructive)]">
              Letzte Synchronisierung fehlgeschlagen: {syncError}
            </p>
          )}
        </div>
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
              {adapter.familySharingToggle && (
                <label className="mb-2 flex items-center gap-2 text-[0.8rem] text-[var(--text-secondary)]">
                  <input
                    type="checkbox"
                    checked={includeFamily}
                    onChange={(e) => setIncludeFamily(e.target.checked)}
                  />
                  Auch mit mir geteilte Geräte (Familienfreigabe) einbeziehen
                </label>
              )}
              <button
                type="button"
                onClick={handleLogin}
                disabled={saving}
                className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60"
              >
                Anmelden
              </button>

              {adapter.importSession && (
                <div className="mt-3 border-t border-[var(--divider)] pt-3">
                  <p className="mb-1 text-[0.78rem] text-[var(--text-secondary)]">
                    Schlägt die Anmeldung mit "GSA 503" fehl? Stattdessen eine
                    Session-Datei hochladen, die auf einem anderen Gerät erzeugt wurde.
                  </p>
                  <label className="flex cursor-pointer items-center justify-center rounded-lg border border-dashed border-[var(--divider)] p-3 text-[0.8rem] text-[var(--text-secondary)]">
                    <input
                      type="file"
                      accept="application/json"
                      onChange={handleImportSession}
                      disabled={saving}
                      className="hidden"
                    />
                    Session-Datei auswählen (account.json)
                  </label>
                </div>
              )}
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
