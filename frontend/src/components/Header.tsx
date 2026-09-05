import type { Airtag } from '../api'
import { usePushNotifications } from '../hooks/usePushNotifications'

interface Props {
  title: string
  airtags: Airtag[]
  currentId: string | null
  onSelect: (id: string) => void
  onOpenManager: () => void
}

export function Header({ title, airtags, currentId, onSelect, onOpenManager }: Props) {
  const push = usePushNotifications()

  return (
    <header className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-2 border-b border-white/10 bg-[#161b22]/90 px-4 pb-3 pt-[calc(0.9rem+env(safe-area-inset-top))] backdrop-blur">
      <h1 className="truncate text-[0.95rem] font-semibold tracking-tight">{title}</h1>
      <div className="flex flex-wrap items-center gap-2">
        {airtags.length > 0 && (
          <select
            className="min-h-10 rounded-lg border border-white/10 bg-[#1c2128] px-3 text-sm"
            value={currentId ?? ''}
            onChange={(e) => onSelect(e.target.value)}
          >
            {airtags.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        )}
        <button
          type="button"
          aria-label="AirTags verwalten"
          title="AirTags verwalten"
          onClick={onOpenManager}
          className="flex h-10 w-10 items-center justify-center rounded-full bg-[#1c2128] hover:bg-white/10"
        >
          ⚙️
        </button>
        <button
          type="button"
          onClick={push.enable}
          disabled={push.status === 'active'}
          className="flex h-10 items-center gap-1 rounded-lg bg-[#238636] px-3 text-sm font-medium text-white hover:bg-[#2ea043] disabled:bg-[#30363d] disabled:text-[#8b949e]"
        >
          {push.status === 'active' ? '✅ Aktiv' : '🔔 Benachrichtigungen'}
        </button>
        <a href="/logout" className="px-2 text-sm text-[#8b949e] hover:text-white">
          Abmelden
        </a>
      </div>
    </header>
  )
}
