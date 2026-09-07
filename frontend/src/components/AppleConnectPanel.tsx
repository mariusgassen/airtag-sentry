import { useEffect, useState } from 'react'
import type { AppleLoginResult, AppleTwoFactorMethod } from '../api'
import { ChevronRightIcon, KeyIcon } from './icons'
import { Row, Section } from './AirtagDetail'

type Step = 'credentials' | 'select-method' | 'code'

export interface AppleConnectAdapter {
  getStatus: () => Promise<{ connected: boolean }>
  login: (email: string, password: string) => Promise<AppleLoginResult>
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
  const [open, setOpen] = useState(false)
  const [step, setStep] = useState<Step>('credentials')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [methods, setMethods] = useState<AppleTwoFactorMethod[]>([])
  const [code, setCode] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    adapter.getStatus().then((s) => setConnected(s.connected))
  }, [adapter])

  async function refreshStatus() {
    setConnected((await adapter.getStatus()).connected)
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
              {connected === null ? '…' : connected ? 'Verbunden' : 'Nicht verbunden'}
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
          <button
            type="button"
            onClick={handleDisconnect}
            className="rounded-lg border border-[var(--destructive)] px-3 py-1.5 text-sm text-[var(--destructive)]"
          >
            Trennen
          </button>
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
