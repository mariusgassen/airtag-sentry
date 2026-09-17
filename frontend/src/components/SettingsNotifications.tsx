import { useState } from 'react'
import type { AppSettings, NotificationTestResult } from '../api'
import { testNotifications } from '../api'
import { BellIcon } from './icons'
import { Row, Section, Switch } from './AirtagDetail'
import { TelegramPanel } from './TelegramPanel'
import { MqttPanel } from './MqttPanel'
import { HaApiTokenPanel } from './HaApiTokenPanel'

interface Props {
  pushStatus: 'idle' | 'active' | 'error'
  pushBusy: boolean
  onEnablePush: () => void
  onDisablePush: () => void
  settings: AppSettings | null
  update: (patch: Partial<AppSettings>, opts?: { immediate?: boolean }) => void
}

const CHANNEL_LABELS: Record<string, string> = {
  telegram: 'Telegram',
  webpush: 'Push',
}

function summarizeTestResults(results: NotificationTestResult[]): string {
  if (results.length === 0) {
    return 'Keine Benachrichtigungskanäle eingerichtet – zuerst Telegram oder Push aktivieren.'
  }
  return results
    .map((r) => `${CHANNEL_LABELS[r.channel] ?? r.channel}: ${r.ok ? 'gesendet ✓' : `fehlgeschlagen (${r.error ?? 'unbekannter Fehler'})`}`)
    .join(' · ')
}

export function SettingsNotifications({
  pushStatus,
  pushBusy,
  onEnablePush,
  onDisablePush,
  settings,
  update,
}: Props) {
  const [testBusy, setTestBusy] = useState(false)
  const [testMessage, setTestMessage] = useState<string | null>(null)

  async function handleTestNotifications() {
    setTestBusy(true)
    setTestMessage(null)
    try {
      const { results } = await testNotifications()
      setTestMessage(summarizeTestResults(results))
    } catch (err) {
      setTestMessage('Test fehlgeschlagen: ' + (err as Error).message)
    } finally {
      setTestBusy(false)
    }
  }

  return (
    <div className="px-3">
      <Section>
        <Row
          icon={<BellIcon className="h-5 w-5" filled={pushStatus === 'active'} />}
          label="Push-Benachrichtigungen"
          trailing={
            <Switch
              checked={pushStatus === 'active'}
              disabled={pushBusy}
              onChange={(v) => (v ? onEnablePush() : onDisablePush())}
            />
          }
          bordered={false}
        />
        <Row
          label="Test-Benachrichtigung"
          trailing={
            <button
              type="button"
              onClick={handleTestNotifications}
              disabled={testBusy}
              className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60"
            >
              {testBusy ? 'Sende…' : 'Senden'}
            </button>
          }
        />
      </Section>
      {testMessage && (
        <p className="mb-2 mt-2 px-1 text-[0.78rem] text-[var(--text-secondary)]">{testMessage}</p>
      )}
      <TelegramPanel />
      <MqttPanel />
      <HaApiTokenPanel />

      <p className="mb-2 mt-6 px-1 text-[0.75rem] font-medium uppercase tracking-wide text-[var(--text-secondary)]">
        Bei folgenden Ereignissen benachrichtigen
      </p>
      <Section>
        <Row
          label="Unerwartete Bewegung"
          trailing={
            settings && (
              <Switch
                checked={settings.notify_on_distance_threshold}
                onChange={(v) => update({ notify_on_distance_threshold: v }, { immediate: true })}
              />
            )
          }
          bordered={false}
        />
        <Row
          label="Bewegung nach Stillstand"
          trailing={
            settings && (
              <Switch
                checked={settings.notify_on_stillstand_movement}
                onChange={(v) => update({ notify_on_stillstand_movement: v }, { immediate: true })}
              />
            )
          }
        />
        <Row
          label="Zurückgelassen"
          trailing={
            settings && (
              <Switch
                checked={settings.notify_on_left_behind}
                onChange={(v) => update({ notify_on_left_behind: v }, { immediate: true })}
              />
            )
          }
        />
        <Row
          label="Eigenständige Bewegung"
          trailing={
            settings && (
              <Switch
                checked={settings.notify_on_autonomous_movement}
                onChange={(v) => update({ notify_on_autonomous_movement: v }, { immediate: true })}
              />
            )
          }
        />
      </Section>
      <p className="mb-2 px-1 text-[0.72rem] text-[var(--text-secondary)]">
        "Zurückgelassen": du hast dich von einem stillstehenden Objekt entfernt - routinemäßig, z. B. wenn
        du dein Laptop zu Hause lässt. "Eigenständige Bewegung": das Objekt selbst hat sich ohne dich
        bewegt. "Zurückgelassen" wird nicht gemeldet, wenn das Objekt an einem hinterlegten Ort
        (Einstellungen → Orte) liegen bleibt.
      </p>
      <p className="mb-2 px-1 text-[0.72rem] text-[var(--text-secondary)]">
        Gilt für alle Kanäle oben. Ein deaktiviertes Ereignis wird weiterhin im Verlauf aufgezeichnet, löst
        aber keine Benachrichtigung aus.
      </p>
    </div>
  )
}
