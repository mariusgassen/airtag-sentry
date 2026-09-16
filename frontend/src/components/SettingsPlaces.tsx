import { useEffect, useRef, useState } from 'react'
import { MapContainer, TileLayer, ZoomControl } from 'react-leaflet'
import type { AddressSearchResult, Place } from '../api'
import { createPlace, deletePlace, searchAddress, updatePlace } from '../api'
import { Row, Section } from './AirtagDetail'
import { EditableCircle } from './EditableCircle'
import { ChevronRightIcon, MapPinIcon, PlusIcon, TrashIcon } from './icons'
import { useCurrentPosition } from '../hooks/useCurrentPosition'

const DEFAULT_RADIUS_METERS = 100
// Initial center for a brand-new place before browser geolocation resolves
// (or if it's unavailable/denied) - PlaceEditor's effect swaps this for the
// real fix once/if one arrives and the user hasn't started editing yet (see
// useCurrentPosition and the `mapGeneration` effect below).
const FALLBACK_CENTER: [number, number] = [51.1657, 10.4515]

// A location already known elsewhere in the app (a map popup's "Ort hier
// hinzufügen") - seeds a brand-new place at that exact spot instead of
// FALLBACK_CENTER/geolocation, so a geofence can be created from a location
// the user already found rather than re-finding it by panning/searching
// from scratch (see App.tsx's onAddPlace/placeSeed).
export interface PlaceSeed {
  lat: number
  lon: number
  name?: string
}

interface Props {
  places: Place[]
  onChanged: () => void | Promise<void>
  seed?: PlaceSeed | null
  onSeedConsumed?: () => void
}

export function SettingsPlaces({ places, onChanged, seed = null, onSeedConsumed }: Props) {
  const [editing, setEditing] = useState<Place | 'new' | null>(null)

  // A seed arriving (from a map popup) always opens straight into a new
  // place's editor, even if the user was sitting on the plain list.
  useEffect(() => {
    if (seed) setEditing('new')
  }, [seed])

  if (editing !== null) {
    return (
      <PlaceEditor
        place={editing === 'new' ? null : editing}
        seed={editing === 'new' ? seed : null}
        onDone={async () => {
          setEditing(null)
          onSeedConsumed?.()
          await onChanged()
        }}
        onCancel={() => {
          setEditing(null)
          onSeedConsumed?.()
        }}
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

const SEARCH_DEBOUNCE_MS = 400
const MIN_QUERY_LENGTH = 3

/** Address search box overlaid on the place editor's map - without it,
 * finding a geofence's center meant panning/zooming by hand or relying on
 * the browser's current position, with no way to jump straight to a known
 * address. Debounced-as-you-type against the backend's Nominatim proxy
 * (geocode.py's search_address via GET /api/geocode/search); picking a
 * result recenters the map through the same `onSelect` path a manual drag
 * or a seeded location uses. */
function AddressSearch({ onSelect }: { onSelect: (lat: number, lon: number) => void }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<AddressSearchResult[]>([])
  const [open, setOpen] = useState(false)
  const debounceRef = useRef<number | null>(null)

  useEffect(() => {
    if (debounceRef.current !== null) window.clearTimeout(debounceRef.current)
    const trimmed = query.trim()
    if (trimmed.length < MIN_QUERY_LENGTH) {
      setResults([])
      return
    }
    debounceRef.current = window.setTimeout(() => {
      searchAddress(trimmed)
        .then(setResults)
        .catch(() => setResults([]))
    }, SEARCH_DEBOUNCE_MS)
    return () => {
      if (debounceRef.current !== null) window.clearTimeout(debounceRef.current)
    }
  }, [query])

  return (
    <div className="absolute left-2 right-12 top-2 z-[500]">
      <input
        value={query}
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        placeholder="Adresse suchen…"
        className="w-full rounded-lg border border-[var(--divider)] bg-[var(--surface)] px-3 py-2 text-sm shadow outline-none focus:border-[var(--accent)]"
      />
      {open && results.length > 0 && (
        <ul className="mt-1 max-h-48 overflow-y-auto rounded-lg border border-[var(--divider)] bg-[var(--surface)] shadow-lg">
          {results.map((r) => (
            <li key={`${r.lat},${r.lon}`}>
              <button
                type="button"
                onClick={() => {
                  onSelect(r.lat, r.lon)
                  setQuery(r.display_name)
                  setOpen(false)
                }}
                className="block w-full px-3 py-2 text-left text-sm hover:bg-[var(--surface-2)]"
              >
                {r.display_name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function PlaceEditor({
  place,
  seed,
  onDone,
  onCancel,
}: {
  place: Place | null
  // Only meaningful when `place` is null (a brand-new place) - see PlaceSeed.
  seed?: PlaceSeed | null
  onDone: () => void | Promise<void>
  onCancel: () => void
}) {
  const here = useCurrentPosition()
  const [name, setName] = useState(place?.name ?? seed?.name ?? '')
  // Seeded at FALLBACK_CENTER for a brand-new, un-seeded place, not `here` -
  // browser geolocation is asynchronous by spec, so `here` is guaranteed to
  // still be null on this very first render even when it goes on to resolve
  // a moment later. The effect below is what actually applies a late-
  // resolving fix; a `seed` (an already-known location from a map popup)
  // takes priority over both, since it's a location the user explicitly
  // picked, not a fallback.
  const [center, setCenter] = useState<[number, number]>(
    place ? [place.lat, place.lon] : seed ? [seed.lat, seed.lon] : FALLBACK_CENTER,
  )
  const [radius, setRadius] = useState(place?.radius_meters ?? DEFAULT_RADIUS_METERS)
  const [saving, setSaving] = useState(false)
  // Set inside EditableCircle's onChange below the moment the user first
  // drags the circle, or immediately for a seeded place - once true, a
  // geolocation fix resolving afterwards must never override an already-
  // meaningful center (the user's in-progress edit, or the seed itself).
  const hasUserEditedRef = useRef(seed != null)
  // Bumped exactly once, the first time browser geolocation resolves for a
  // brand-new place the user hasn't touched yet. MapContainer's `center`
  // prop and EditableCircle's underlying L.circle layer are both only ever
  // applied at mount time (see EditableCircle's own mount-once comment), so
  // merely calling setCenter here wouldn't move anything already on screen -
  // changing this key remounts the map + circle at the real location.
  const [mapGeneration, setMapGeneration] = useState(0)

  useEffect(() => {
    if (place || !here || hasUserEditedRef.current) return
    setCenter(here)
    setMapGeneration((g) => g + 1)
  }, [place, here])

  function handleAddressSelect(lat: number, lon: number) {
    hasUserEditedRef.current = true
    setCenter([lat, lon])
    setMapGeneration((g) => g + 1)
  }

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
      <div className="relative h-64 shrink-0">
        <MapContainer
          key={mapGeneration}
          center={center}
          zoom={16}
          zoomControl={false}
          className="h-full w-full"
        >
          {/* topright, not the default topleft - AddressSearch below spans
              the top of the map and would otherwise sit right under it. */}
          <ZoomControl position="topright" />
          <TileLayer
            attribution="&copy; OpenStreetMap contributors"
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <EditableCircle
            center={center}
            radius={radius}
            onChange={(nextCenter, nextRadius) => {
              hasUserEditedRef.current = true
              setCenter(nextCenter)
              setRadius(nextRadius)
            }}
          />
        </MapContainer>
        <AddressSearch onSelect={handleAddressSelect} />
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
