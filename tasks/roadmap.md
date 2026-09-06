# Roadmap

A forward-looking, prioritized backlog — distinct from `tasks/todo.md`,
which is the historical changelog of what's already shipped (v1–v10).
Items here are ideas and their rationale, not commitments; each gets moved
into `todo.md` (with a `vN:` entry) as it's actually built.

Compared against [Traccar](https://www.traccar.org/) (a mature open-source
GPS platform) for feature inspiration where noted below.

## 1. "Moved without you" alert correlation — in progress

Find My (and this app's existing movement detection) can tell you an item
moved *relative to its own history*, but not whether it moved *while you
weren't with it* — the actual signal that distinguishes "someone took my
bike from the garage while I was at work" from "I rode my bike to the
store." Apple's `FindMy.py`/search-party protocol (used for AirTags) mostly
only reports a device that's off, dead, or in airplane mode, so a live
phone's location has to come from a different source: Apple's classic Find
My iPhone web service (`fmipservice`, the same one behind `icloud.com/find`)
via the `pyicloud` library, as a second, independent Apple session/login.

Produces a new `moved_without_owner` alert reason, fired *in addition to*
(never replacing) the existing movement alerts, when a real movement alert
already fired **and** the tag's new position is far from the owner's
last-known phone location.

Status: **done** — see `tasks/todo.md` v11.

## 2. Visualize owner location on the map

Fast-follow to (1): a distinct marker for the owner's last-known position,
reusing `MapCard.tsx`'s existing pulsing "Aktueller Standort" dot pattern
but sourced from the new `GET /api/owner-location` endpoint instead of the
browser's own geolocation. Small, mostly frontend.

## 3. Home/geofence zone

Traccar-style: define a home/safe zone (radius or drawn polygon) per AirTag
or globally; alert specifically on leaving it, with optional dwell-time and
schedule rules (e.g. only armed overnight). Doesn't need any phone-tracking
infrastructure at all — a good self-contained complement to (1)/(2) for
anyone who doesn't want a second Apple login, and a proven pattern (Traccar
users rely on this as their primary alerting mechanism).

## 4. Alert history view

The `alerts` table already stores full history; the dashboard only ever
surfaces the single latest one (`/api/status`'s `last_alert`). Cheap, high
value: a scrollable list per AirTag, same shape as the existing
"Verlauf" (location history) collapsible section in `AirtagDetail.tsx`.

## 5. Trip/stop report per AirTag

Traccar-style: "here's every place it stayed more than X minutes this
week," built entirely from existing `location_reports` — no new data
source needed, just a report view over what's already stored.

## 6. Per-AirTag alert snooze

Mute alerts for a chosen duration (e.g. "I'm riding my own bike right now")
without touching the global movement thresholds in Settings. Standard
false-positive-fatigue mitigation for any motion-based alarm.

## 7. Per-AirTag notification routing

Every configured notifier (ntfy/Telegram/push) currently fires for every
AirTag. Multi-item households may want e.g. only Telegram for the bike,
only push for the backpack.

## 8. Location-history retention/pruning

`location_reports` grows unbounded. Add a retention-period setting and a
periodic prune job (or a `DELETE ... WHERE timestamp < now() - interval`
run alongside the scheduler).

## 9. Battery-level surfacing

`FindMy.py`'s location report exposes a `status` byte for the accessory,
which likely encodes battery state (needs confirming against the library/
protocol). If so: surface it in the dashboard and optionally alert on low
battery, so a dying AirTag doesn't just silently stop reporting.

## 10. CSV/GPX export

Export an AirTag's location history for a given period — useful when
reporting a theft to police.
