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
}

export function SettingsNotifications({ pushStatus, pushBusy, onEnablePush, onDisablePush }: Props) {
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
    </div>
  )
}
