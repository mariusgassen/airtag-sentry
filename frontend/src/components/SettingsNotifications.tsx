import type { AppSettings } from '../api'
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

export function SettingsNotifications({
  pushStatus,
  pushBusy,
  onEnablePush,
  onDisablePush,
  settings,
  update,
}: Props) {
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
      </Section>
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
          label="Bewegung ohne dich"
          trailing={
            settings && (
              <Switch
                checked={settings.notify_on_moved_without_owner}
                onChange={(v) => update({ notify_on_moved_without_owner: v }, { immediate: true })}
              />
            )
          }
        />
      </Section>
      <p className="mb-2 px-1 text-[0.72rem] text-[var(--text-secondary)]">
        Gilt für alle Kanäle oben. Ein deaktiviertes Ereignis wird weiterhin im Verlauf aufgezeichnet, löst
        aber keine Benachrichtigung aus.
      </p>
    </div>
  )
}
