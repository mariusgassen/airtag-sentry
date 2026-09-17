import type { ReactNode } from 'react'
import { AirtagGlyph, ClockIcon, GearIcon } from './icons'

export type TabKey = 'objects' | 'timeline' | 'settings'

interface Props {
  active: TabKey
  onChange: (tab: TabKey) => void
}

function TabButton({
  label,
  icon,
  selected,
  onClick,
}: {
  label: string
  icon: ReactNode
  selected: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={selected ? 'page' : undefined}
      className={`flex flex-1 flex-col items-center gap-0.5 pb-[calc(0.25rem+env(safe-area-inset-bottom))] pt-1.5 text-[0.65rem] ${
        selected ? 'text-[var(--accent)]' : 'text-[var(--text-secondary)]'
      }`}
    >
      {icon}
      {label}
    </button>
  )
}

/** Persistent bottom tab bar, styled after Find My's own (Personen/Geräte/
 * Objekte/Ich). This app only has one kind of tracked thing, so it collapses
 * to three tabs: the AirTag list/detail flow, the cross-object Zeitachse
 * (timeline), and settings - which used to be a view pushed on top of the
 * list behind a gear icon, easy to lose track of since nothing showed it was
 * open. A real tab reads as "always there" instead. */
export function TabBar({ active, onChange }: Props) {
  return (
    <nav className="chrome-blur pointer-events-auto flex shrink-0 border-t border-[var(--divider)]">
      <TabButton
        label="Objekte"
        icon={<AirtagGlyph className="h-6 w-6" />}
        selected={active === 'objects'}
        onClick={() => onChange('objects')}
      />
      <TabButton
        label="Zeitachse"
        icon={<ClockIcon className="h-6 w-6" />}
        selected={active === 'timeline'}
        onClick={() => onChange('timeline')}
      />
      <TabButton
        label="Einstellungen"
        icon={<GearIcon className="h-6 w-6" />}
        selected={active === 'settings'}
        onClick={() => onChange('settings')}
      />
    </nav>
  )
}
