import type { Airtag, OwnerDevice, TimelineVisit } from '../api'
import { airtagColor } from '../airtagColor'
import { capitalize, deviceLabel, formatClusterRange, formatDayHeading, formatRelative } from '../format'
import { mapsUrl } from '../maps'
import { staticMapTileUrl } from '../staticMapTile'
import { AirtagAvatar } from './AirtagAvatar'
import { DeviceAvatar } from './DeviceAvatar'
import { ClockIcon, LocationArrowIcon, MapPinIcon } from './icons'

/** Which single object (if any) the feed/map pane are narrowed to - see
 * App.tsx's handleTimelineFilterChange. */
export type TimelineFilter = { type: 'airtag' | 'device'; id: string } | null

/** Groups newest-first visits (already sorted that way by GET /api/timeline)
 * into calendar-day buckets, preserving order within and across days. */
function groupByDay(visits: TimelineVisit[]): { heading: string; visits: TimelineVisit[] }[] {
  const groups: { heading: string; visits: TimelineVisit[] }[] = []
  for (const visit of visits) {
    const heading = formatDayHeading(visit.start)
    const current = groups[groups.length - 1]
    if (current?.heading === heading) {
      current.visits.push(visit)
    } else {
      groups.push({ heading, visits: [visit] })
    }
  }
  return groups
}

/** Opens visit.label's Nominatim/POI page when there's a real matched place
 * (a geofence's or POI's OSM data), so "more info" has somewhere real to go
 * beyond the coordinates - falls back to the same Maps deep link the map
 * popups use (see maps.ts) when there's nothing more specific. */
function placeInfoUrl(visit: TimelineVisit): string {
  return mapsUrl(visit.lat, visit.lon, visit.label ?? visit.object_name)
}

function VisitRow({ visit, onSelect }: { visit: TimelineVisit; onSelect: () => void }) {
  const isStay = visit.count > 1
  return (
    <button
      type="button"
      onClick={onSelect}
      title={
        isStay
          ? `${new Date(visit.start).toLocaleString()} – ${new Date(visit.end).toLocaleString()}`
          : new Date(visit.start).toLocaleString()
      }
      className="flex w-full items-center gap-3 border-t border-[var(--divider)] px-4 py-2.5 text-left first:border-t-0 hover:bg-white/5"
    >
      {visit.object_type === 'airtag' ? (
        <AirtagAvatar airtag={{ id: visit.object_id, icon: visit.object_icon, color: visit.object_color }} size={40} />
      ) : (
        <DeviceAvatar
          device={{
            id: visit.object_id,
            icon: visit.object_icon,
            color: visit.object_color,
            device_type: visit.object_device_type ?? '',
            name: visit.object_name,
          }}
          size={40}
        />
      )}
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          <span className="block truncate text-[0.95rem] font-medium">{visit.label ?? visit.object_name}</span>
          {/* Only a real place name needs the object name spelled out
              separately - an unnamed place has nothing to disambiguate from,
              so its title is just the object name with no dangling "· " in
              front of it (raw coordinates aren't a place name worth showing
              here either; the address line below already covers "where"
              when one's resolved). */}
          {visit.label && (
            <span className="shrink-0 text-[0.8rem] text-[var(--text-secondary)]">· {visit.object_name}</span>
          )}
        </span>
        {/* The "public info about places" line - the raw geocoded address
            behind the resolved label above, same data stay.label is built
            from (see stays.py's resolve_label), shown here instead of
            collapsed into just the name. */}
        {visit.address && (
          <span className="flex items-center gap-1 truncate text-[0.8rem] text-[var(--text-secondary)]">
            <MapPinIcon className="h-3 w-3 shrink-0" />
            <span className="truncate">{visit.address}</span>
          </span>
        )}
        <span className="flex items-center gap-2 text-[0.8rem] text-[var(--text-secondary)]">
          <span className="flex items-center gap-1">
            <ClockIcon className="h-3 w-3 shrink-0" />
            {isStay
              ? `${formatClusterRange(visit.start, visit.end)} · ${visit.count}×`
              : capitalize(formatRelative(visit.start))}
          </span>
          {/* A real, external link (not just this row's own onSelect) - lets
              a visit be opened straight into Maps for directions/street view
              instead of only ever re-centering this app's own map. Nested
              inside the row's own button - stopPropagation keeps it from
              also firing onSelect. */}
          <button
            type="button"
            aria-label="In Maps öffnen"
            title="In Maps öffnen"
            onClick={(e) => {
              e.stopPropagation()
              window.open(placeInfoUrl(visit), '_blank', 'noopener,noreferrer')
            }}
            className="flex items-center gap-0.5 text-[var(--accent)]"
          >
            <LocationArrowIcon className="h-3 w-3 shrink-0" />
            Maps
          </button>
        </span>
      </span>
      {/* Small "picture" of the place - a real OSM map tile (same source/
          license as the app's own live maps), lazy-loaded so a long scroll
          doesn't fire a burst of tile requests at once. Not a POI photo
          (Nominatim doesn't provide one) but a genuine map image, closer to
          Google Timeline's per-visit thumbnail than a bare address line. */}
      <img
        src={staticMapTileUrl(visit.lat, visit.lon)}
        alt=""
        loading="lazy"
        className="h-12 w-12 shrink-0 rounded-lg object-cover"
      />
    </button>
  )
}

function FilterChip({
  label,
  color,
  selected,
  onClick,
}: {
  label: string
  color?: string
  selected: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-[0.8rem] font-medium ${
        selected
          ? 'border-[var(--accent)] bg-[var(--accent)]/15 text-[var(--accent)]'
          : 'border-[var(--divider)] text-[var(--text-secondary)]'
      }`}
    >
      {color && <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: color }} />}
      <span className="max-w-[8rem] truncate">{label}</span>
    </button>
  )
}

// null = "all available history" - GET /api/timeline's own default (see
// App.tsx's timelineRangeDays); 'today' is client-side only (see below) -
// the backend only understands a day-count lookback, which for "today"
// would mean a rolling 24h window in the *server's* UTC clock rather than
// the viewer's own local calendar day, silently clipping or including the
// wrong hours depending on timezone and time of day.
export type TimelineRange = number | null | 'today'

const RANGE_OPTIONS: { label: string; value: TimelineRange }[] = [
  { label: 'Alle', value: null },
  { label: 'Heute', value: 'today' },
  { label: '7 Tage', value: 7 },
  { label: '30 Tage', value: 30 },
  { label: '90 Tage', value: 90 },
]

/** Aggregate, cross-object "Google Timeline" style feed - every AirTag's and
 * every tracked owner device's stays (see GET /api/timeline), grouped by
 * calendar day and shown newest-first, each stop's place info (resolved
 * label + raw address) shown alongside it. Deliberately a plain list rather
 * than embedding its own map: a visit here already carries its object's
 * identity, and picking one (or a filter chip) hands off to that object's
 * own MapCard/DeviceMapCard in App.tsx's map pane (see onSelectVisit/
 * onFilterChange) rather than duplicating that map's trail/selection logic
 * in a second place. */
export function TimelinePage({
  visits,
  airtags,
  devices,
  filter,
  onFilterChange,
  onSelectVisit,
  rangeDays,
  onRangeChange,
}: {
  visits: TimelineVisit[]
  airtags: Airtag[]
  devices: OwnerDevice[]
  filter: TimelineFilter
  onFilterChange: (filter: TimelineFilter) => void
  onSelectVisit: (visit: TimelineVisit) => void
  // A numeric/null range is already applied server-side (see App.tsx's
  // refreshTimeline) - `visits` contains that range's data already. 'today'
  // is applied here instead (see TimelineRange's comment), on top of
  // whatever range was fetched (always "all" when 'today' is selected - see
  // App.tsx).
  rangeDays: TimelineRange
  onRangeChange: (range: TimelineRange) => void
}) {
  const filtered = filter ? visits.filter((v) => v.object_type === filter.type && v.object_id === filter.id) : visits
  const rangeFiltered =
    rangeDays === 'today' ? filtered.filter((v) => formatDayHeading(v.start) === 'Heute') : filtered
  const groups = groupByDay(rangeFiltered)

  return (
    <div className="flex h-full flex-col">
      <div className="px-4 pb-2 pt-[0.9rem]">
        <h1 className="text-[1.7rem] font-bold tracking-tight">Zeitachse</h1>
      </div>
      {(airtags.length > 0 || devices.length > 0) && (
        <div className="mb-1 flex gap-2 overflow-x-auto px-4 pb-2">
          <FilterChip label="Alle" selected={filter === null} onClick={() => onFilterChange(null)} />
          {airtags.map((a) => (
            <FilterChip
              key={a.id}
              label={a.name}
              color={a.color ?? airtagColor(a.id)}
              selected={filter?.type === 'airtag' && filter.id === a.id}
              onClick={() => onFilterChange({ type: 'airtag', id: a.id })}
            />
          ))}
          {devices.map((d) => (
            <FilterChip
              key={d.id}
              label={deviceLabel(d)}
              color={d.color ?? airtagColor(d.id)}
              selected={filter?.type === 'device' && filter.id === d.id}
              onClick={() => onFilterChange({ type: 'device', id: d.id })}
            />
          ))}
        </div>
      )}
      <div className="mb-1 flex gap-2 overflow-x-auto px-4 pb-2">
        {RANGE_OPTIONS.map((opt) => (
          <FilterChip
            key={opt.label}
            label={opt.label}
            selected={rangeDays === opt.value}
            onClick={() => onRangeChange(opt.value)}
          />
        ))}
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-[calc(0.75rem+env(safe-area-inset-bottom))]">
        {groups.length === 0 ? (
          <div className="mx-1 rounded-2xl bg-[var(--surface)] p-6 text-center text-sm text-[var(--text-secondary)]">
            {filter || rangeDays ? 'Keine Standortverläufe für diese Auswahl.' : 'Noch keine Standortverläufe vorhanden.'}
          </div>
        ) : (
          groups.map((group) => (
            <div key={group.heading} className="mb-4">
              <p className="mb-2 px-2 text-[0.75rem] font-medium uppercase tracking-wide text-[var(--text-secondary)]">
                {group.heading}
              </p>
              <div className="overflow-hidden rounded-2xl bg-[var(--surface)]">
                {group.visits.map((visit) => (
                  <VisitRow
                    key={`${visit.object_type}-${visit.object_id}-${visit.start}`}
                    visit={visit}
                    onSelect={() => onSelectVisit(visit)}
                  />
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
