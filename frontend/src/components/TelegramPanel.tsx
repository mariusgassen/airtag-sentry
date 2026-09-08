import { useEffect, useState } from 'react'
import {
  deleteTelegramCredentials,
  disableTelegramCommands,
  enableTelegramCommands,
  getTelegramStatus,
  setTelegramCredentials,
} from '../api'
import { ChevronRightIcon, PaperPlaneIcon } from './icons'
import { Row, Section, Switch } from './AirtagDetail'

export function TelegramPanel() {
  const [connected, setConnected] = useState<boolean | null>(null)
  const [chatId, setChatId] = useState<string | null>(null)
  const [botCommandsEnabled, setBotCommandsEnabled] = useState(false)
  const [commandsBusy, setCommandsBusy] = useState(false)
  const [commandsError, setCommandsError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [botToken, setBotToken] = useState('')
  const [chatIdInput, setChatIdInput] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getTelegramStatus().then((s) => {
      setConnected(s.connected)
      setChatId(s.chat_id)
      setBotCommandsEnabled(s.bot_commands_enabled)
    })
  }, [])

  async function refreshStatus() {
    const s = await getTelegramStatus()
    setConnected(s.connected)
    setChatId(s.chat_id)
    setBotCommandsEnabled(s.bot_commands_enabled)
  }

  async function handleToggleCommands() {
    setCommandsBusy(true)
    setCommandsError(null)
    try {
      if (botCommandsEnabled) {
        await disableTelegramCommands()
      } else {
        await enableTelegramCommands()
      }
      await refreshStatus()
    } catch (err) {
      setCommandsError((err as Error).message)
    } finally {
      setCommandsBusy(false)
    }
  }

  function reset() {
    setBotToken('')
    setChatIdInput('')
    setError(null)
  }

  async function handleSave() {
    if (!botToken.trim() || !chatIdInput.trim()) {
      setError('Bitte Bot-Token und Chat-ID eingeben.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await setTelegramCredentials(botToken.trim(), chatIdInput.trim())
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
    if (!confirm('Telegram wirklich trennen?')) return
    await deleteTelegramCredentials()
    await refreshStatus()
  }

  return (
    <Section>
      <Row
        icon={<PaperPlaneIcon className="h-5 w-5" />}
        label="Telegram"
        trailing={
          <span className="flex items-center gap-2">
            <span className={`text-sm ${connected ? 'text-[var(--success)]' : 'text-[var(--text-secondary)]'}`}>
              {connected === null ? '…' : connected ? `Verbunden · ${chatId}` : 'Nicht verbunden'}
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
            <div>
              <p className="text-sm font-medium">Bot-Befehle</p>
              <p className="text-[0.78rem] text-[var(--text-secondary)]">
                /list und /where direkt im Chat abfragen.
              </p>
            </div>
            <Switch checked={botCommandsEnabled} onChange={handleToggleCommands} disabled={commandsBusy} />
          </div>
          {commandsError && <p className="mt-2 text-[0.78rem] text-[var(--destructive)]">{commandsError}</p>}

          <button
            type="button"
            onClick={handleDisconnect}
            className="mt-3 rounded-lg border border-[var(--destructive)] px-3 py-1.5 text-sm text-[var(--destructive)]"
          >
            Trennen
          </button>
        </div>
      )}

      {open && !connected && (
        <div className="border-t border-[var(--divider)] p-3">
          <input
            autoFocus
            value={botToken}
            onChange={(e) => setBotToken(e.target.value)}
            placeholder="Bot-Token (von @BotFather)"
            className="mb-2 w-full rounded-lg border border-[var(--divider)] bg-[var(--surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
          />
          <input
            value={chatIdInput}
            onChange={(e) => setChatIdInput(e.target.value)}
            placeholder="Chat-ID"
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
