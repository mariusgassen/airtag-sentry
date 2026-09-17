import type { TimelineVisit } from '../api'
import { capitalize, formatClusterRange, formatDayHeading, formatRelative } from '../format'
import { mapsUrl } from '../maps'
import { staticMapTileUrl } from '../staticMapTile'
import { AirtagAvatar } from './AirtagAvatar'
import { DeviceAvatar } from './DeviceAvatar'
import { ClockIcon, LocationArrowIcon, MapPinIcon } from './icons'

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
          <span className="block truncate text-[0.95rem] font-medium">
            {visit.label ?? `${visit.lat.toFixed(4)}, ${visit.lon.toFixed(4)}`}
          </span>
          <span className="shrink-0 text-[0.8rem] text-[var(--text-secondary)]">· {visit.object_name}</span>
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
              inside the row's own button, same as StayRow.tsx's correction
              button - stopPropagation keeps it from also firing onSelect. */}
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

/** Aggregate, cross-object "Google Timeline" style feed - every AirTag's and
 * every tracked owner device's stays (see GET /api/timeline), grouped by
 * calendar day and shown newest-first, each stop's place info (resolved
 * label + raw address) shown alongside it. Deliberately a plain list rather
 * than embedding its own map: a visit here already carries its object's
 * identity, and picking one deep-links into that object's own MapCard/
 * DeviceMapCard (see onSelectVisit) rather than duplicating that map's trail/
 * selection logic in a second place. */
export function TimelinePage({
  visits,
  onSelectVisit,
}: {
  visits: TimelineVisit[]
  onSelectVisit: (visit: TimelineVisit) => void
}) {
  const groups = groupByDay(visits)

  return (
    <div className="flex h-full flex-col">
      <div className="px-4 pb-2 pt-[0.9rem]">
        <h1 className="text-[1.7rem] font-bold tracking-tight">Zeitachse</h1>
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-[calc(0.75rem+env(safe-area-inset-bottom))]">
        {groups.length === 0 ? (
          <div className="mx-1 rounded-2xl bg-[var(--surface)] p-6 text-center text-sm text-[var(--text-secondary)]">
            Noch keine Standortverläufe vorhanden.
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
