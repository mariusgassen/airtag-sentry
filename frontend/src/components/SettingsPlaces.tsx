import { useState } from 'react'
import { MapContainer, TileLayer } from 'react-leaflet'
import type { Place } from '../api'
import { createPlace, deletePlace, updatePlace } from '../api'
import { Row, Section } from './AirtagDetail'
import { EditableCircle } from './EditableCircle'
import { ChevronRightIcon, MapPinIcon, PlusIcon, TrashIcon } from './icons'
import { useCurrentPosition } from '../hooks/useCurrentPosition'

const DEFAULT_RADIUS_METERS = 100
// Only used if browser geolocation is unavailable when adding a brand-new
// place - immediately overridden once/if it resolves (see useCurrentPosition).
const FALLBACK_CENTER: [number, number] = [51.1657, 10.4515]

interface Props {
  places: Place[]
  onChanged: () => void | Promise<void>
}

export function SettingsPlaces({ places, onChanged }: Props) {
  const [editing, setEditing] = useState<Place | 'new' | null>(null)

  if (editing !== null) {
    return (
      <PlaceEditor
        place={editing === 'new' ? null : editing}
        onDone={async () => {
          setEditing(null)
          await onChanged()
        }}
        onCancel={() => setEditing(null)}
      />
    )
  }

  return (
    <div className="px-3">
      <Section>
        {places.map((p) => (
          <Row
            key={p.id}
            icon={<MapPinIcon className="h-5 w-5" />}
            label={p.name}
            trailing={
              <span className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
                {Math.round(p.radius_meters)} m
                <ChevronRightIcon className="h-4 w-4" />
              </span>
            }
            onClick={() => setEditing(p)}
          />
        ))}
        <Row
          icon={<PlusIcon className="h-5 w-5" />}
          label="Ort hinzufügen"
          onClick={() => setEditing('new')}
          bordered={places.length > 0}
        />
      </Section>
    </div>
  )
}

function PlaceEditor({
  place,
  onDone,
  onCancel,
}: {
  place: Place | null
  onDone: () => void | Promise<void>
  onCancel: () => void
}) {
  const here = useCurrentPosition()
  const [name, setName] = useState(place?.name ?? '')
  const [center, setCenter] = useState<[number, number]>(
    place ? [place.lat, place.lon] : (here ?? FALLBACK_CENTER),
  )
  const [radius, setRadius] = useState(place?.radius_meters ?? DEFAULT_RADIUS_METERS)
  const [saving, setSaving] = useState(false)

  async function save() {
    const trimmed = name.trim()
    if (!trimmed) return
    setSaving(true)
    try {
      const input = { name: trimmed, lat: center[0], lon: center[1], radius_meters: radius }
      if (place) {
        await updatePlace(place.id, input)
      } else {
        await createPlace(input)
      }
      await onDone()
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete() {
    if (!place) return
    if (!confirm(`"${place.name}" wirklich entfernen?`)) return
    setSaving(true)
    try {
      await deletePlace(place.id)
      await onDone()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-center justify-between px-3 pb-1 pt-[0.6rem]">
        <button type="button" onClick={onCancel} className="text-[0.95rem] text-[var(--accent)]">
          Abbrechen
        </button>
        <button
          type="button"
          onClick={save}
          disabled={saving || !name.trim()}
          className="text-[0.95rem] font-semibold text-[var(--accent)] disabled:opacity-40"
        >
          Sichern
        </button>
      </div>
      <div className="h-64 shrink-0">
        <MapContainer center={center} zoom={16} className="h-full w-full">
          <TileLayer
            attribution="&copy; OpenStreetMap contributors"
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <EditableCircle
            center={center}
            radius={radius}
            onChange={(nextCenter, nextRadius) => {
              setCenter(nextCenter)
              setRadius(nextRadius)
            }}
          />
        </MapContainer>
      </div>
      <div className="flex-1 overflow-y-auto p-3">
        <Section>
          <div className="border-t border-[var(--divider)] p-3 first:border-t-0">
            <label className="mb-1.5 block text-[0.72rem] font-medium uppercase tracking-wide text-[var(--text-secondary)]">
              Name
            </label>
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="z. B. Zuhause"
              className="w-full rounded-lg border border-[var(--divider)] bg-[var(--surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
            />
          </div>
          <div className="flex items-center justify-between border-t border-[var(--divider)] p-3">
            <span className="text-[0.95rem]">Radius</span>
            <span className="text-sm text-[var(--text-secondary)]">{Math.round(radius)} m</span>
          </div>
        </Section>
        {place && (
          <Section>
            <Row
              icon={<TrashIcon className="h-5 w-5" />}
              label="Ort entfernen"
              destructive
              onClick={handleDelete}
              bordered={false}
            />
          </Section>
        )}
      </div>
    </div>
  )
}
