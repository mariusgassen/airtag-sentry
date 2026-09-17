import { useState } from 'react'
import type { FormEvent } from 'react'
import type { CSSProperties } from 'react'
import { DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors } from '@dnd-kit/core'
import type { DragEndEvent } from '@dnd-kit/core'
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import type { Airtag, OwnerDevice, OwnerLocation, Status } from '../api'
import { capitalize, deviceLabel, formatAirtagBattery, formatDeviceBattery, formatRelative } from '../format'
import { AirtagAvatar } from './AirtagAvatar'
import { DeviceAvatar } from './DeviceAvatar'
import { ChevronRightIcon, DragHandleIcon, PlusIcon, RefreshIcon, StarIcon } from './icons'

interface Props {
  airtags: Airtag[]
  statuses: Record<string, Status>
  currentId: string | null
  onSelectAirtag: (id: string) => void
  onCreate: (name: string) => Promise<void>
  // Persists a full drag-and-drop reorder of `airtags` (see App.tsx's
  // handleReorderAirtags / PUT /api/airtags/order). Mirrors
  // onReorderDevices below - see CLAUDE.md's AirTag/owner-device parity rule.
  onReorderAirtags: (airtagIds: string[]) => void
  // Only rendered when the owner-tracking Apple account (see
  // owner_tracking.py / Settings -> Apple-Konten) is connected.
  ownerConnected: boolean
  // Every *enabled* (tracked) owner device (Settings -> Eigene Geräte) -
  // this list is the first place a tracked device becomes visible, not
  // just the Settings panel it started in (see tasks/todo.md v15).
  // Already in the user's chosen display order (see db.py's
  // set_owner_devices_order) - render as given, don't re-sort.
  devices: OwnerDevice[]
  // Latest recorded location per device, keyed by device_id - absent for a
  // device that's never returned a fix yet.
  deviceLocations: Record<string, OwnerLocation>
  selectedDeviceId: string | null
  onSelectDevice: (id: string) => void
  // Persists a full drag-and-drop reorder of `devices` (see App.tsx's
  // handleReorderDevices / PUT /api/owner-devices/order).
  onReorderDevices: (deviceIds: string[]) => void
  // Manual "refresh now" (POST /api/poll-now) - triggers an immediate poll
  // instead of waiting for the scheduled interval, see App.tsx.
  onRefresh: () => void
  refreshing: boolean
}

function DeviceRow({
  device,
  location,
  selected,
  editing,
  showHandle,
  isFirst,
  onSelect,
}: {
  device: OwnerDevice
  location: OwnerLocation | undefined
  selected: boolean
  editing: boolean
  showHandle: boolean
  isFirst: boolean
  onSelect: (id: string) => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: device.id,
    disabled: !editing,
  })
  const style: CSSProperties = { transform: CSS.Transform.toString(transform), transition }
  const content = (
    <>
      <DeviceAvatar device={device} size={40} />
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          <span className="block truncate text-[0.95rem] font-medium">{deviceLabel(device)}</span>
          {device.is_primary && <StarIcon className="h-3.5 w-3.5 shrink-0 text-[var(--accent)]" filled />}
        </span>
        {device.on_account === false ? (
          <span className="block truncate text-[0.8rem] text-[var(--destructive)]">
            Nicht mehr im iCloud-Account gefunden
          </span>
        ) : (
          <span className="block truncate text-[0.8rem] text-[var(--text-secondary)]">
            {location
              ? capitalize(formatRelative(location.recorded_at)) +
                (location.battery_level != null
                  ? ` · ${formatDeviceBattery(location.battery_level, location.battery_status)}`
                  : '')
              : 'Kein Standort verfügbar'}
          </span>
        )}
      </span>
    </>
  )
  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`bg-[var(--surface)] ${isDragging ? 'relative z-10 opacity-90' : ''} ${
        !isFirst ? 'border-t border-[var(--divider)]' : ''
      }`}
    >
      {editing ? (
        <div className="flex items-center gap-3 px-3 py-2.5">
          {content}
          {showHandle && (
            <button
              type="button"
              {...attributes}
              {...listeners}
              aria-label="Zum Sortieren ziehen"
              title="Zum Sortieren ziehen"
              className="flex h-8 w-8 shrink-0 touch-none items-center justify-center text-[var(--text-secondary)] active:cursor-grabbing"
            >
              <DragHandleIcon className="h-4 w-4" />
            </button>
          )}
        </div>
      ) : (
        <button
          type="button"
          onClick={() => onSelect(device.id)}
          className={`flex w-full items-center gap-3 px-3 py-2.5 text-left ${
            selected ? 'bg-[var(--accent)]/15' : 'hover:bg-white/5'
          }`}
        >
          {content}
          <ChevronRightIcon className="h-4 w-4 shrink-0 text-[var(--text-secondary)]" />
        </button>
      )}
    </div>
  )
}

function AirtagRow({
  airtag,
  subtitle,
  selected,
  editing,
  showHandle,
  isFirst,
  onSelect,
}: {
  airtag: Airtag
  subtitle: string
  selected: boolean
  editing: boolean
  showHandle: boolean
  isFirst: boolean
  onSelect: (id: string) => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: airtag.id,
    disabled: !editing,
  })
  const style: CSSProperties = { transform: CSS.Transform.toString(transform), transition }
  const content = (
    <>
      <AirtagAvatar airtag={airtag} size={40} />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[0.95rem] font-medium">{airtag.name}</span>
        <span className="block truncate text-[0.8rem] text-[var(--text-secondary)]">{subtitle}</span>
      </span>
    </>
  )
  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`bg-[var(--surface)] ${isDragging ? 'relative z-10 opacity-90' : ''} ${
        !isFirst ? 'border-t border-[var(--divider)]' : ''
      }`}
    >
      {editing ? (
        <div className="flex items-center gap-3 px-3 py-2.5">
          {content}
          {showHandle && (
            <button
              type="button"
              {...attributes}
              {...listeners}
              aria-label="Zum Sortieren ziehen"
              title="Zum Sortieren ziehen"
              className="flex h-8 w-8 shrink-0 touch-none items-center justify-center text-[var(--text-secondary)] active:cursor-grabbing"
            >
              <DragHandleIcon className="h-4 w-4" />
            </button>
          )}
        </div>
      ) : (
        <button
          type="button"
          onClick={() => onSelect(airtag.id)}
          className={`flex w-full items-center gap-3 px-3 py-2.5 text-left ${
            selected ? 'bg-[var(--accent)]/15' : 'hover:bg-white/5'
          }`}
        >
          {content}
          <ChevronRightIcon className="h-4 w-4 shrink-0 text-[var(--text-secondary)]" />
        </button>
      )}
    </div>
  )
}

/** Grouped "Objekte" list: every AirTag plus every tracked owner device
 * (Macs, iPhones, iPads, Watches - see owner_tracking.py), each in its own
 * labeled group. A device's own location history only shows once you've
 * selected it here (DeviceDetail) - Settings only manages which devices
 * are tracked, not their history (see tasks/todo.md for the version that
 * moved it here).
 *
 * "Bearbeiten" toggles an edit mode (both groups at once) where rows swap
 * their nav chevron for a drag handle - dragging persists the new order via
 * onReorderAirtags/onReorderDevices, which just resend the whole reordered
 * id list to the same PUT endpoints the old up/down buttons used. */
export function ObjectsList({
  airtags,
  statuses,
  currentId,
  onSelectAirtag,
  onCreate,
  onReorderAirtags,
  ownerConnected,
  devices,
  deviceLocations,
  selectedDeviceId,
  onSelectDevice,
  onReorderDevices,
  onRefresh,
  refreshing,
}: Props) {
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState(false)

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  async function handleAdd(e: FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setSaving(true)
    try {
      await onCreate(name.trim())
      setName('')
      setAdding(false)
    } finally {
      setSaving(false)
    }
  }

  function handleDeviceDragEnd(event: DragEndEvent) {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIndex = devices.findIndex((d) => d.id === active.id)
    const newIndex = devices.findIndex((d) => d.id === over.id)
    onReorderDevices(arrayMove(devices, oldIndex, newIndex).map((d) => d.id))
  }

  function handleAirtagDragEnd(event: DragEndEvent) {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIndex = airtags.findIndex((a) => a.id === active.id)
    const newIndex = airtags.findIndex((a) => a.id === over.id)
    onReorderAirtags(arrayMove(airtags, oldIndex, newIndex).map((a) => a.id))
  }

  // Keeps "Fertig" reachable even if the list that made reordering worth
  // offering shrinks to one item while already editing.
  const canReorder = airtags.length > 1 || (ownerConnected && devices.length > 1)

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between px-4 pb-2 pt-[0.9rem]">
        <h1 className="text-[1.7rem] font-bold tracking-tight">Objekte</h1>
        <div className="flex items-center gap-1">
          {(canReorder || editing) && (
            <button
              type="button"
              onClick={() => setEditing((v) => !v)}
              className={`px-2 text-[0.95rem] text-[var(--accent)] ${editing ? 'font-semibold' : ''}`}
            >
              {editing ? 'Fertig' : 'Bearbeiten'}
            </button>
          )}
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            aria-label="Jetzt aktualisieren"
            title="Jetzt aktualisieren"
            className="flex h-9 w-9 items-center justify-center rounded-full text-[var(--accent)] hover:bg-[var(--surface)] disabled:opacity-60"
          >
            <RefreshIcon className={`h-5 w-5 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
          <button
            type="button"
            onClick={() => setAdding((v) => !v)}
            aria-label="AirTag hinzufügen"
            title="AirTag hinzufügen"
            className="flex h-9 w-9 items-center justify-center rounded-full text-[var(--accent)] hover:bg-[var(--surface)]"
          >
            <PlusIcon className="h-5 w-5" />
          </button>
        </div>
      </div>

      {adding && (
        <form onSubmit={handleAdd} className="mx-4 mb-2 flex gap-2">
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Name, z. B. Fahrrad"
            className="flex-1 rounded-lg border border-[var(--divider)] bg-[var(--surface)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
          />
          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            Hinzufügen
          </button>
        </form>
      )}

      <div className="flex-1 overflow-y-auto px-2 pb-[calc(0.75rem+env(safe-area-inset-bottom))]">
        {ownerConnected && (
          <div className="mb-4">
            <p className="mb-2 px-2 text-[0.75rem] font-medium uppercase tracking-wide text-[var(--text-secondary)]">
              Geräte
            </p>
            {devices.length === 0 ? (
              <div className="mx-1 rounded-2xl bg-[var(--surface)] p-4 text-center text-sm text-[var(--text-secondary)]">
                Keine Geräte verfolgt. In den Einstellungen unter „Eigene Geräte“ auswählen.
              </div>
            ) : (
              <div
                className={`overflow-hidden rounded-2xl bg-[var(--surface)] ${refreshing ? 'animate-pulse' : ''}`}
              >
                <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDeviceDragEnd}>
                  <SortableContext items={devices.map((d) => d.id)} strategy={verticalListSortingStrategy}>
                    {devices.map((d, i) => (
                      <DeviceRow
                        key={d.id}
                        device={d}
                        location={deviceLocations[d.id]}
                        selected={d.id === selectedDeviceId}
                        editing={editing}
                        showHandle={devices.length > 1}
                        isFirst={i === 0}
                        onSelect={onSelectDevice}
                      />
                    ))}
                  </SortableContext>
                </DndContext>
              </div>
            )}
          </div>
        )}

        <p className="mb-2 px-2 text-[0.75rem] font-medium uppercase tracking-wide text-[var(--text-secondary)]">
          AirTags
        </p>
        {airtags.length === 0 ? (
          <div className="mx-1 rounded-2xl bg-[var(--surface)] p-6 text-center text-sm text-[var(--text-secondary)]">
            Noch keine AirTags.
            <br />
            Tippe auf <PlusIcon className="inline h-3.5 w-3.5 align-[-1px]" />, um eines hinzuzufügen.
          </div>
        ) : (
          <div className={`overflow-hidden rounded-2xl bg-[var(--surface)] ${refreshing ? 'animate-pulse' : ''}`}>
            <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleAirtagDragEnd}>
              <SortableContext items={airtags.map((a) => a.id)} strategy={verticalListSortingStrategy}>
                {airtags.map((a, i) => {
                  const status = statuses[a.id]
                  const subtitle = status?.last_report
                    ? capitalize(formatRelative(status.last_report.timestamp)) +
                      (status.last_report.battery_level
                        ? ` · ${formatAirtagBattery(status.last_report.battery_level)}`
                        : '')
                    : 'Kein Standort verfügbar'
                  return (
                    <AirtagRow
                      key={a.id}
                      airtag={a}
                      subtitle={subtitle}
                      selected={a.id === currentId}
                      editing={editing}
                      showHandle={airtags.length > 1}
                      isFirst={i === 0}
                      onSelect={onSelectAirtag}
                    />
                  )
                })}
              </SortableContext>
            </DndContext>
          </div>
        )}
      </div>
    </div>
  )
}
