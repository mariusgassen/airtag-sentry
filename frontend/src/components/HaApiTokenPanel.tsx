import { useEffect, useState } from 'react'
import { generateHaToken, getHaTokenStatus, revokeHaToken } from '../api'
import { HomeAssistantIcon } from './icons'
import { Row, Section } from './AirtagDetail'

/** For a cloud-hosted AirTag Sentry: Home Assistant polls GET /api/ha/state
 * itself (no inbound access into the home network needed), authenticated by
 * this bearer token - the counterpart to MqttPanel's push model, which only
 * works when both run on the same network. */
export function HaApiTokenPanel() {
  const [configured, setConfigured] = useState<boolean | null>(null)
  const [newToken, setNewToken] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    refreshStatus()
  }, [])

  async function refreshStatus() {
    const s = await getHaTokenStatus()
    setConfigured(s.configured)
  }

  async function handleGenerate() {
    if (configured && !confirm('Neuen Token erzeugen? Der bisherige Token funktioniert danach nicht mehr.')) {
      return
    }
    setBusy(true)
    try {
      const { token } = await generateHaToken()
      setNewToken(token)
      await refreshStatus()
    } finally {
      setBusy(false)
    }
  }

  async function handleRevoke() {
    if (!confirm('API-Zugriff für Home Assistant wirklich widerrufen?')) return
    await revokeHaToken()
    setNewToken(null)
    await refreshStatus()
  }

  return (
    <Section>
      <Row
        icon={<HomeAssistantIcon className="h-5 w-5" />}
        label="Home Assistant (REST-Abruf)"
        trailing={
          <span className={`text-sm ${configured ? 'text-[var(--success)]' : 'text-[var(--text-secondary)]'}`}>
            {configured === null ? '…' : configured ? 'Token aktiv' : 'Kein Token'}
          </span>
        }
        bordered={false}
      />
      <div className="border-t border-[var(--divider)] p-3">
        <p className="mb-3 text-[0.78rem] text-[var(--text-secondary)]">
          Für ein cloudgehostetes AirTag Sentry, das dein lokales Home Assistant nicht per MQTT erreichen kann: HA
          ruft <code>/api/ha/state</code> selbst per REST-Sensor ab, mit diesem Token als Bearer-Auth.
        </p>
        {newToken && (
          <div className="mb-3 rounded-lg border border-[var(--accent)] bg-[var(--surface-2)] p-3">
            <p className="mb-1 text-[0.78rem] font-medium">Wird nur einmal angezeigt - jetzt kopieren:</p>
            <code className="block break-all text-sm">{newToken}</code>
          </div>
        )}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleGenerate}
            disabled={busy}
            className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60"
          >
            {configured ? 'Token neu erzeugen' : 'Token erzeugen'}
          </button>
          {configured && (
            <button
              type="button"
              onClick={handleRevoke}
              className="rounded-lg border border-[var(--destructive)] px-3 py-1.5 text-sm font-medium text-[var(--destructive)]"
            >
              Widerrufen
            </button>
          )}
        </div>
      </div>
    </Section>
  )
}
