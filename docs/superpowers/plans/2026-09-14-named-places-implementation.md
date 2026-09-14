# Named Places Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move history "stays" from client-side clustering to a backend concept, and add persisted place labels (auto-detected POI names + user corrections) and user-defined geofences ("Home", "Office"), so future dwell-time-stats/cross-device-comparison/export features have a shared foundation to build on.

**Architecture:** A new pure `stays.py` module (mirrors `movement.py`'s DB-free style) clusters raw reports/locations into "stays" at query time. Two new persistence layers - a DB-backed geocode cache + user corrections (replacing `geocode.py`'s in-memory cache, populated by the poller instead of live at render time) and user-defined circular geofences (`named_places`) - feed a label-resolution priority chain (geofence > correction > cached POI name > cached address). `/api/reports` and `/api/owner-devices/history` return both raw points (for the trail) and fully-labeled stays; the frontend renders what it's given instead of recomputing clusters/labels itself.

**Tech Stack:** FastAPI + psycopg (backend), React + Leaflet + react-leaflet (frontend), new `@geoman-io/leaflet-geoman-free` dependency for the geofence's drag-to-edit circle.

**Spec:** `docs/superpowers/specs/2026-09-14-named-places-design.md`

## Global Constraints

- No backward-compatibility shims - this is pre-production software (see CLAUDE.md). The in-memory geocode cache and client-side `clustering.ts` are replaced outright, not kept alongside the new path.
- Single-user, single-account app - `named_places` has no per-device/per-user scoping.
- AirTag `Report`s have a numeric `id` and arrive oldest-first; owner-device `OwnerLocation`s have no `id` in the API response (keyed by `recorded_at`) and arrive newest-first. Every stay-shaped type/function that touches both must preserve this asymmetry rather than flattening it (see CLAUDE.md).
- Any map/history feature must ship for both AirTags and owner devices in the same task, never as a follow-up (see CLAUDE.md's parity constraint).
- Verification before calling any task done: `pytest` against a real local Postgres, and for frontend tasks `cd frontend && npx tsc -b && npx vite build && npx oxlint`. No frontend test runner exists in this repo - don't add one.

---

## Task 1: `named_places` table (geofences)

**Files:**
- Create: `alembic/versions/c4f8a2d91e56_named_places.py`
- Modify: `airtag_sentry/db.py` (add `NamedPlace` dataclass after `HaApiToken`, line ~158; add CRUD functions at end of file, after `fetch_owner_device_location_history`)
- Test: `tests/test_db.py`

**Interfaces:**
- Produces: `NamedPlace(id: int, name: str, lat: float, lon: float, radius_meters: float)`; `list_named_places(conn) -> list[NamedPlace]`; `create_named_place(conn, name: str, lat: float, lon: float, radius_meters: float) -> NamedPlace`; `update_named_place(conn, place_id: int, name: str, lat: float, lon: float, radius_meters: float) -> NamedPlace | None`; `delete_named_place(conn, place_id: int) -> None`.

- [ ] **Step 1: Write the migration**

```python
"""named places

Revision ID: c4f8a2d91e56
Revises: a1c7e5f2b8d4
Create Date: 2026-09-15 00:00:00.000000

User-defined circular geofences ("Home", "Office") - see
docs/superpowers/specs/2026-09-14-named-places-design.md. Global, not
per-device: a place is a physical location, meaningful regardless of which
AirTag/owner device visits it (single-user app, see CLAUDE.md).
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4f8a2d91e56'
down_revision: Union[str, Sequence[str], None] = 'a1c7e5f2b8d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE named_places (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            name TEXT NOT NULL,
            lat DOUBLE PRECISION NOT NULL,
            lon DOUBLE PRECISION NOT NULL,
            radius_meters DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS named_places")
```

- [ ] **Step 2: Add the `NamedPlace` dataclass to `db.py`**

Insert after the `HaApiToken` dataclass (`airtag_sentry/db.py`, currently ending around line 158, right before `@dataclasses.dataclass(frozen=True)\nclass AppSettings:`):

```python
@dataclasses.dataclass(frozen=True)
class NamedPlace:
    id: int
    name: str
    lat: float
    lon: float
    radius_meters: float
```

- [ ] **Step 3: Write the failing tests**

Add to `tests/test_db.py` (add `NamedPlace`, `create_named_place`, `delete_named_place`, `list_named_places`, `update_named_place` to the existing `from airtag_sentry.db import (...)` block, alphabetically):

```python
def test_named_places_crud_round_trip(conn):
    assert list_named_places(conn) == []

    home = create_named_place(conn, "Zuhause", 49.8728, 8.6512, 75.0)
    assert home.name == "Zuhause"
    assert list_named_places(conn) == [home]

    updated = update_named_place(conn, home.id, "Home", 49.87, 8.65, 100.0)
    assert updated == NamedPlace(id=home.id, name="Home", lat=49.87, lon=8.65, radius_meters=100.0)
    assert list_named_places(conn) == [updated]

    delete_named_place(conn, home.id)
    assert list_named_places(conn) == []


def test_update_named_place_returns_none_for_unknown_id(conn):
    assert update_named_place(conn, 999999, "X", 0, 0, 1) is None
```

Also add `named_places` to the `conn` fixture's `TRUNCATE` list (`tests/test_db.py`, the fixture at line ~60-94):

```python
                cur.execute(
                    "TRUNCATE airtags, location_reports, alerts, push_subscriptions, airtag_keys, "
                    "owner_devices, owner_device_locations, owner_apple_credentials, telegram_settings, "
                    "mqtt_settings, ha_api_tokens, named_places "
                    "RESTART IDENTITY CASCADE"
                )
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_db.py -k named_place -v`
Expected: FAIL with `ImportError` (functions/dataclass don't exist yet) or `NameError`.

- [ ] **Step 5: Implement the CRUD functions**

Append to the end of `airtag_sentry/db.py` (after `fetch_owner_device_location_history`):

```python
def list_named_places(conn: psycopg.Connection) -> list[NamedPlace]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, lat, lon, radius_meters FROM named_places ORDER BY name")
        return [NamedPlace(*row) for row in cur.fetchall()]


def create_named_place(
    conn: psycopg.Connection, name: str, lat: float, lon: float, radius_meters: float
) -> NamedPlace:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO named_places (name, lat, lon, radius_meters) VALUES (%s, %s, %s, %s) "
            "RETURNING id, name, lat, lon, radius_meters",
            (name, lat, lon, radius_meters),
        )
        row = cur.fetchone()
    conn.commit()
    return NamedPlace(*row)


def update_named_place(
    conn: psycopg.Connection, place_id: int, name: str, lat: float, lon: float, radius_meters: float
) -> NamedPlace | None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE named_places SET name = %s, lat = %s, lon = %s, radius_meters = %s WHERE id = %s "
            "RETURNING id, name, lat, lon, radius_meters",
            (name, lat, lon, radius_meters, place_id),
        )
        row = cur.fetchone()
    conn.commit()
    return NamedPlace(*row) if row else None


def delete_named_place(conn: psycopg.Connection, place_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM named_places WHERE id = %s", (place_id,))
    conn.commit()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_db.py -k named_place -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add alembic/versions/c4f8a2d91e56_named_places.py airtag_sentry/db.py tests/test_db.py
git commit -m "Add named_places table and CRUD for user-defined geofences"
```

---

## Task 2: Geocode cache + corrections persistence

**Files:**
- Create: `alembic/versions/d7b3e6a04f21_geocoded_points.py`
- Modify: `airtag_sentry/db.py` (add `GeocodedPoint` dataclass after `NamedPlace`; add rounding helper + CRUD functions at end of file)
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `round_coord(lat: float, lon: float) -> tuple[float, float]`; `GeocodedPoint(lat_rounded: float, lon_rounded: float, address: str | None, poi_name: str | None)`; `get_geocoded_point(conn, lat: float, lon: float) -> GeocodedPoint | None`; `store_geocoded_point(conn, lat: float, lon: float, address: str | None, poi_name: str | None) -> GeocodedPoint`; `get_place_label_correction(conn, lat: float, lon: float) -> str | None`; `set_place_label_correction(conn, lat: float, lon: float, corrected_name: str) -> None`; `delete_place_label_correction(conn, lat: float, lon: float) -> None`.

- [ ] **Step 1: Write the migration**

```python
"""geocoded points and place label corrections

Revision ID: d7b3e6a04f21
Revises: c4f8a2d91e56
Create Date: 2026-09-15 00:05:00.000000

Replaces geocode.py's in-memory `_cache` dict with a persisted table
populated by the poller (tracker.py) instead of lazily at render time - see
docs/superpowers/specs/2026-09-14-named-places-design.md. Both tables are
keyed by the same ~1m-precision rounded coordinate (see db.round_coord) so a
correction overrides exactly the same lookup the geocode cache uses.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd7b3e6a04f21'
down_revision: Union[str, Sequence[str], None] = 'c4f8a2d91e56'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE geocoded_points (
            lat_rounded DOUBLE PRECISION NOT NULL,
            lon_rounded DOUBLE PRECISION NOT NULL,
            address TEXT,
            poi_name TEXT,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (lat_rounded, lon_rounded)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE place_label_corrections (
            lat_rounded DOUBLE PRECISION NOT NULL,
            lon_rounded DOUBLE PRECISION NOT NULL,
            corrected_name TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (lat_rounded, lon_rounded)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS place_label_corrections")
    op.execute("DROP TABLE IF EXISTS geocoded_points")
```

- [ ] **Step 2: Add the `GeocodedPoint` dataclass**

Insert in `airtag_sentry/db.py`, right after the `NamedPlace` dataclass added in Task 1:

```python
@dataclasses.dataclass(frozen=True)
class GeocodedPoint:
    lat_rounded: float
    lon_rounded: float
    address: str | None
    poi_name: str | None
```

- [ ] **Step 3: Write the failing tests**

Add to `tests/test_db.py` (extend the import block with `GeocodedPoint`, `round_coord`, `get_geocoded_point`, `store_geocoded_point`, `get_place_label_correction`, `set_place_label_correction`, `delete_place_label_correction`):

```python
def test_round_coord_matches_at_one_meter_precision():
    # ~1m precision (5 decimals) - two fixes a meter apart round to the same
    # key and share one geocode lookup/correction.
    assert round_coord(49.87281, 8.65123) == round_coord(49.872814, 8.651233)
    assert round_coord(49.87281, 8.65123) != round_coord(49.8730, 8.6512)


def test_geocoded_point_round_trip_and_upsert(conn):
    assert get_geocoded_point(conn, 49.8728, 8.6512) is None

    stored = store_geocoded_point(conn, 49.8728, 8.6512, "12 Main St", "REWE")
    assert stored == GeocodedPoint(lat_rounded=49.8728, lon_rounded=8.6512, address="12 Main St", poi_name="REWE")
    assert get_geocoded_point(conn, 49.8728, 8.6512) == stored

    # Storing again for the same (rounded) coordinate overwrites, not duplicates.
    updated = store_geocoded_point(conn, 49.87280001, 8.65120001, "12 Main St", "REWE Markt")
    assert updated.poi_name == "REWE Markt"
    assert get_geocoded_point(conn, 49.8728, 8.6512) == updated


def test_place_label_correction_round_trip(conn):
    assert get_place_label_correction(conn, 49.8728, 8.6512) is None

    set_place_label_correction(conn, 49.8728, 8.6512, "My Corner Store")
    assert get_place_label_correction(conn, 49.8728, 8.6512) == "My Corner Store"

    set_place_label_correction(conn, 49.8728, 8.6512, "Corrected Again")
    assert get_place_label_correction(conn, 49.8728, 8.6512) == "Corrected Again"

    delete_place_label_correction(conn, 49.8728, 8.6512)
    assert get_place_label_correction(conn, 49.8728, 8.6512) is None
```

Add `geocoded_points, place_label_corrections` to the `conn` fixture's `TRUNCATE` list (same edit site as Task 1):

```python
                cur.execute(
                    "TRUNCATE airtags, location_reports, alerts, push_subscriptions, airtag_keys, "
                    "owner_devices, owner_device_locations, owner_apple_credentials, telegram_settings, "
                    "mqtt_settings, ha_api_tokens, named_places, geocoded_points, place_label_corrections "
                    "RESTART IDENTITY CASCADE"
                )
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_db.py -k "geocoded_point or place_label_correction or round_coord" -v`
Expected: FAIL with `ImportError`/`NameError`.

- [ ] **Step 5: Implement the rounding helper and CRUD functions**

Append to the end of `airtag_sentry/db.py`:

```python
def round_coord(lat: float, lon: float) -> tuple[float, float]:
    """~1m precision - shared by geocoded_points and place_label_corrections
    so a correction overrides exactly the lookup the geocode cache uses."""
    return (round(lat, 5), round(lon, 5))


def get_geocoded_point(conn: psycopg.Connection, lat: float, lon: float) -> GeocodedPoint | None:
    lat_r, lon_r = round_coord(lat, lon)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT lat_rounded, lon_rounded, address, poi_name FROM geocoded_points "
            "WHERE lat_rounded = %s AND lon_rounded = %s",
            (lat_r, lon_r),
        )
        row = cur.fetchone()
        return GeocodedPoint(*row) if row else None


def store_geocoded_point(
    conn: psycopg.Connection, lat: float, lon: float, address: str | None, poi_name: str | None
) -> GeocodedPoint:
    lat_r, lon_r = round_coord(lat, lon)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO geocoded_points (lat_rounded, lon_rounded, address, poi_name)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (lat_rounded, lon_rounded) DO UPDATE SET
                address = EXCLUDED.address, poi_name = EXCLUDED.poi_name, fetched_at = now()
            RETURNING lat_rounded, lon_rounded, address, poi_name
            """,
            (lat_r, lon_r, address, poi_name),
        )
        row = cur.fetchone()
    conn.commit()
    return GeocodedPoint(*row)


def get_place_label_correction(conn: psycopg.Connection, lat: float, lon: float) -> str | None:
    lat_r, lon_r = round_coord(lat, lon)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT corrected_name FROM place_label_corrections WHERE lat_rounded = %s AND lon_rounded = %s",
            (lat_r, lon_r),
        )
        row = cur.fetchone()
        return row[0] if row else None


def set_place_label_correction(conn: psycopg.Connection, lat: float, lon: float, corrected_name: str) -> None:
    lat_r, lon_r = round_coord(lat, lon)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO place_label_corrections (lat_rounded, lon_rounded, corrected_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (lat_rounded, lon_rounded) DO UPDATE SET corrected_name = EXCLUDED.corrected_name
            """,
            (lat_r, lon_r, corrected_name),
        )
    conn.commit()


def delete_place_label_correction(conn: psycopg.Connection, lat: float, lon: float) -> None:
    lat_r, lon_r = round_coord(lat, lon)
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM place_label_corrections WHERE lat_rounded = %s AND lon_rounded = %s", (lat_r, lon_r)
        )
    conn.commit()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_db.py -k "geocoded_point or place_label_correction or round_coord" -v`
Expected: PASS

- [ ] **Step 7: Fix a pre-existing test-isolation gap while touching this fixture**

The `conn` fixture's settings-reset `UPDATE` (`tests/test_db.py`, same block as the `TRUNCATE` above) never resets `history_cluster_radius_meters`, so a test that changes it (`test_update_settings_round_trips`) can leak into a later test if run order ever changes. Fix it in the same edit:

```python
                cur.execute(
                    """
                    UPDATE settings SET
                        polling_interval_minutes = 15,
                        movement_distance_threshold_meters = 100,
                        movement_stillstand_hours = 24,
                        movement_stillstand_movement_meters = 15,
                        movement_alert_on_backfill = false,
                        movement_away_distance_meters = 150,
                        owner_location_max_age_minutes = 60,
                        history_cluster_radius_meters = 50
                    WHERE id = 1
                    """
                )
```

- [ ] **Step 8: Run the full test_db.py suite to confirm no regressions**

Run: `pytest tests/test_db.py -v`
Expected: PASS (all tests, including the pre-existing ones)

- [ ] **Step 9: Commit**

```bash
git add alembic/versions/d7b3e6a04f21_geocoded_points.py airtag_sentry/db.py tests/test_db.py
git commit -m "Add geocoded_points and place_label_corrections persistence"
```

---

## Task 3: `stays.py` - pure clustering and label resolution

**Files:**
- Create: `airtag_sentry/stays.py`
- Test: `tests/test_stays.py`

**Interfaces:**
- Consumes: `NamedPlace` from `airtag_sentry.db` (Task 1); `haversine_distance` from `airtag_sentry.movement`.
- Produces: `Stay[T](points: list[T], anchor: T)`; `cluster_by_proximity(points: list[T], get_lat_lon: Callable[[T], tuple[float, float]], radius_meters: float) -> list[Stay[T]]`; `match_place(lat: float, lon: float, places: list[NamedPlace]) -> NamedPlace | None`; `resolve_label(place: NamedPlace | None, corrected_name: str | None, poi_name: str | None, address: str | None) -> str | None`.

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from airtag_sentry.db import NamedPlace
from airtag_sentry.stays import Stay, cluster_by_proximity, match_place, resolve_label


def _get_lat_lon(point: tuple[float, float]) -> tuple[float, float]:
    return point


def test_cluster_by_proximity_groups_consecutive_nearby_points():
    points = [(49.8728, 8.6512), (49.8729, 8.6513), (49.9000, 8.7000)]

    stays = cluster_by_proximity(points, _get_lat_lon, radius_meters=50)

    assert len(stays) == 2
    assert stays[0] == Stay(points=[points[0], points[1]], anchor=points[0])
    assert stays[1] == Stay(points=[points[2]], anchor=points[2])


def test_cluster_by_proximity_empty_input():
    assert cluster_by_proximity([], _get_lat_lon, radius_meters=50) == []


def test_cluster_by_proximity_anchor_does_not_drift():
    # Each point within 50m of the *first* point in the run, but the run as a
    # whole drifts further than 50m end-to-end - still one stay, since every
    # point is compared to the anchor, not the previous point.
    anchor = (49.87280, 8.65120)
    points = [anchor, (49.87282, 8.65122), (49.87284, 8.65124), (49.87286, 8.65126)]

    stays = cluster_by_proximity(points, _get_lat_lon, radius_meters=50)

    assert len(stays) == 1
    assert stays[0].anchor == anchor


def test_match_place_returns_none_when_no_place_contains_the_point():
    assert match_place(49.8728, 8.6512, []) is None
    far_place = NamedPlace(id=1, name="Far away", lat=0.0, lon=0.0, radius_meters=10)
    assert match_place(49.8728, 8.6512, [far_place]) is None


def test_match_place_smallest_radius_wins_on_overlap():
    home = NamedPlace(id=1, name="Home", lat=49.8728, lon=8.6512, radius_meters=100)
    office_nook = NamedPlace(id=2, name="Home office", lat=49.8728, lon=8.6512, radius_meters=10)

    assert match_place(49.8728, 8.6512, [home, office_nook]) == office_nook
    assert match_place(49.8728, 8.6512, [office_nook, home]) == office_nook


def test_resolve_label_priority_chain():
    place = NamedPlace(id=1, name="Home", lat=0, lon=0, radius_meters=1)

    assert resolve_label(place, "correction", "poi", "address") == "Home"
    assert resolve_label(None, "correction", "poi", "address") == "correction"
    assert resolve_label(None, None, "poi", "address") == "poi"
    assert resolve_label(None, None, None, "address") == "address"
    assert resolve_label(None, None, None, None) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stays.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'airtag_sentry.stays'`

- [ ] **Step 3: Implement `stays.py`**

```python
"""Pure "stay" clustering and place-label resolution logic.

No DB or network access here on purpose, so this stays trivially
unit-testable - same rationale as movement.py. Ported from
frontend/src/clustering.ts's clusterByProximity, now the single
implementation both AirTag reports and owner-device locations share (see
docs/superpowers/specs/2026-09-14-named-places-design.md for why this moved
server-side).
"""

from __future__ import annotations

import dataclasses
from typing import Callable, Generic, TypeVar

from airtag_sentry.db import NamedPlace
from airtag_sentry.movement import haversine_distance

T = TypeVar("T")


@dataclasses.dataclass(frozen=True)
class Stay(Generic[T]):
    """A run of consecutive points that stayed within a radius of their
    anchor - see cluster_by_proximity. `points` preserves the input array's
    order (oldest-first for Report, newest-first for OwnerLocation - see
    CLAUDE.md's asymmetry), so callers know which end is "earliest"."""

    points: list[T]
    anchor: T


def cluster_by_proximity(
    points: list[T],
    get_lat_lon: Callable[[T], tuple[float, float]],
    radius_meters: float,
) -> list[Stay[T]]:
    """Groups consecutive points that stay within `radius_meters` of a shared
    anchor into one Stay. Anchor-based (not point-to-point): each point is
    compared to the anchor that started its stay, not the previous point, so
    slow drift can't chain a stay indefinitely away from where it started
    (same idea as movement.py's stillstand-anchor walk). Direction-agnostic -
    only neighboring array entries are ever compared, so this works the same
    for an oldest-first array (Report) or a newest-first one (OwnerLocation).
    """
    stays: list[Stay[T]] = []

    for point in points:
        current = stays[-1] if stays else None
        if current is not None:
            a_lat, a_lon = get_lat_lon(current.anchor)
            lat, lon = get_lat_lon(point)
            if haversine_distance(a_lat, a_lon, lat, lon) <= radius_meters:
                current.points.append(point)
                continue
        stays.append(Stay(points=[point], anchor=point))

    return stays


def match_place(lat: float, lon: float, places: list[NamedPlace]) -> NamedPlace | None:
    """Which geofence (if any) contains this point - smallest-radius match
    wins on overlap, so a small place nested inside a larger one (e.g. "Home
    office" inside "Home") takes priority for points inside the smaller one.
    """
    matches = [p for p in places if haversine_distance(lat, lon, p.lat, p.lon) <= p.radius_meters]
    if not matches:
        return None
    return min(matches, key=lambda p: p.radius_meters)


def resolve_label(
    place: NamedPlace | None,
    corrected_name: str | None,
    poi_name: str | None,
    address: str | None,
) -> str | None:
    """geofence name > user correction > cached POI name > cached address > None."""
    if place is not None:
        return place.name
    if corrected_name is not None:
        return corrected_name
    if poi_name is not None:
        return poi_name
    return address
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stays.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add airtag_sentry/stays.py tests/test_stays.py
git commit -m "Add stays.py: pure stay clustering and place-label resolution"
```

---

## Task 4: `geocode.py` rewrite - `GeocodeResult`, drop in-memory cache

**Files:**
- Modify: `airtag_sentry/geocode.py`
- Modify: `airtag_sentry/web/app.py:36` (import), `:684-686` (the `/api/geocode` route)
- Test: `tests/test_geocode.py`

**Interfaces:**
- Produces: `GeocodeResult(address: str | None, poi_name: str | None)`; `reverse_geocode(lat: float, lon: float, timeout: float = 5.0) -> GeocodeResult`.
- Removed: the module-level `_cache` dict and `_cache_key` function (persistence moves to `db.py`'s `geocoded_points`, populated by the poller - Task 5 - not by this module itself).

- [ ] **Step 1: Read the current test file to know what's being replaced**

`tests/test_geocode.py` currently asserts `reverse_geocode(...)` returns a bare string or `None`, and exercises the in-memory `_cache` dict directly. All of that changes shape in this task.

- [ ] **Step 2: Write the failing tests**

Replace `tests/test_geocode.py` entirely with:

```python
from unittest.mock import Mock

import pytest

from airtag_sentry.geocode import GeocodeResult, reverse_geocode


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    # The 1 req/sec throttle is real-time and would make every test slow -
    # tests only concern themselves with the HTTP call/response mapping.
    import airtag_sentry.geocode as geocode_module

    monkeypatch.setattr(geocode_module, "_MIN_INTERVAL_SECONDS", 0.0)


def test_reverse_geocode_returns_address_and_poi_name(monkeypatch):
    mock_response = Mock()
    mock_response.json.return_value = {
        "display_name": "REWE, 12, Musterstraße, Darmstadt, Hessen, 64283, Deutschland",
        "name": "REWE",
    }
    mock_response.raise_for_status = Mock()
    monkeypatch.setattr("requests.get", lambda *a, **k: mock_response)

    result = reverse_geocode(49.8728, 8.6512)

    assert result == GeocodeResult(
        address="REWE, 12, Musterstraße, Darmstadt, Hessen, 64283, Deutschland",
        poi_name="REWE",
    )


def test_reverse_geocode_returns_none_poi_name_for_a_plain_address(monkeypatch):
    # Nominatim omits "name" entirely for a point that isn't a named POI.
    mock_response = Mock()
    mock_response.json.return_value = {"display_name": "Musterstraße 5, Darmstadt"}
    mock_response.raise_for_status = Mock()
    monkeypatch.setattr("requests.get", lambda *a, **k: mock_response)

    result = reverse_geocode(49.8728, 8.6512)

    assert result == GeocodeResult(address="Musterstraße 5, Darmstadt", poi_name=None)


def test_reverse_geocode_returns_empty_result_on_request_failure(monkeypatch):
    import requests

    def raise_error(*a, **k):
        raise requests.RequestException("boom")

    monkeypatch.setattr("requests.get", raise_error)

    result = reverse_geocode(49.8728, 8.6512)

    assert result == GeocodeResult(address=None, poi_name=None)


def test_reverse_geocode_returns_empty_result_on_missing_display_name(monkeypatch):
    mock_response = Mock()
    mock_response.json.return_value = {}
    mock_response.raise_for_status = Mock()
    monkeypatch.setattr("requests.get", lambda *a, **k: mock_response)

    result = reverse_geocode(49.8728, 8.6512)

    assert result == GeocodeResult(address=None, poi_name=None)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_geocode.py -v`
Expected: FAIL (`GeocodeResult` doesn't exist yet; old tests already deleted so no stale-pass confusion)

- [ ] **Step 4: Rewrite `geocode.py`**

Replace `airtag_sentry/geocode.py` entirely with:

```python
"""Reverse geocoding for report/location markers, via OpenStreetMap's
Nominatim - the same OSM data already backing the map tiles, so no separate
API key/account is needed. Best-effort only: a failed or rate-limited lookup
returns an empty GeocodeResult rather than raising, since this is a "nice to
have" label for a marker that already has its lat/lon, never load-bearing.

Results are persisted by callers via db.py's geocoded_points table (the
poller, see tracker.py) rather than cached here - this module now only ever
makes the HTTP call, rate-limited.
"""

from __future__ import annotations

import dataclasses
import threading
import time

import requests

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
# Nominatim's usage policy caps unauthenticated public use at 1 request/sec
# and requires an identifying User-Agent.
_MIN_INTERVAL_SECONDS = 1.0
_USER_AGENT = "AirTagSentry (self-hosted dashboard, reverse-geocode)"

_lock = threading.Lock()
_last_call = 0.0


@dataclasses.dataclass(frozen=True)
class GeocodeResult:
    address: str | None  # Nominatim's display_name - the full formatted address.
    poi_name: str | None  # Nominatim's name - only present for a named POI (shop, amenity, ...).


def reverse_geocode(lat: float, lon: float, timeout: float = 5.0) -> GeocodeResult:
    global _last_call
    with _lock:
        wait = _MIN_INTERVAL_SECONDS - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            resp = requests.get(
                _NOMINATIM_URL,
                params={"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 18},
                headers={"User-Agent": _USER_AGENT},
                timeout=timeout,
            )
            _last_call = time.monotonic()
            resp.raise_for_status()
            body = resp.json()
        except (requests.RequestException, ValueError):
            return GeocodeResult(address=None, poi_name=None)

        return GeocodeResult(address=body.get("display_name"), poi_name=body.get("name"))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_geocode.py -v`
Expected: PASS

- [ ] **Step 6: Update the one remaining caller - `GET /api/geocode`**

This route (`airtag_sentry/web/app.py`) stays - it's still used by `AddressLine`/`getAddress` for the one case that isn't a stay (`NoReportsView`'s current-browser-location fallback popup, see Task 11). Update it for the new return type:

```python
    @app.get("/api/geocode")
    def geocode_route(lat: float, lon: float):
        return {"address": reverse_geocode(lat, lon).address}
```

(Only the body changes - `reverse_geocode(lat, lon)` was previously the bare string.)

- [ ] **Step 7: Run the full backend test suite to confirm no regressions**

Run: `pytest -v`
Expected: PASS (some Task 5/6/7/8 tests won't exist yet - that's expected; nothing existing should newly fail)

- [ ] **Step 8: Commit**

```bash
git add airtag_sentry/geocode.py airtag_sentry/web/app.py tests/test_geocode.py
git commit -m "geocode.py: return GeocodeResult (address + POI name), drop in-memory cache"
```

---

## Task 5: Poll-time geocoding

**Files:**
- Modify: `airtag_sentry/tracker.py`
- Test: `tests/test_tracker.py`

**Interfaces:**
- Consumes: `reverse_geocode` from `airtag_sentry.geocode` (Task 4); `get_geocoded_point`, `store_geocoded_point` from `airtag_sentry.db` (Task 2).
- Produces: `_geocode_new_points(conn, points: list[tuple[float, float]]) -> None` (module-private, called from `_poll_airtag` and `_update_owner_devices`).

- [ ] **Step 1: Read the current poll flow to confirm the two insertion points**

`_poll_airtag` (`airtag_sentry/tracker.py:136-219`) inserts new `Report`s via `insert_reports(conn, reports)` into `newly_inserted` (line 167). `_update_owner_devices` (`airtag_sentry/tracker.py:72-103`) calls `record_owner_device_location(conn, location)` per location (line 89) - every location passed to it is new (owner-device locations aren't deduplicated the way reports are, per the existing `_update_owner_devices` docstring). Geocoding hooks in right after each of those.

- [ ] **Step 2: Write the failing test**

Add to `tests/test_tracker.py` (check the existing imports at the top of the file and add `get_geocoded_point` from `airtag_sentry.db` and `GeocodeResult` from `airtag_sentry.geocode` alongside them):

```python
def test_poll_once_geocodes_newly_inserted_report_coordinates(monkeypatch, conn):
    # Uses the real conn fixture (test_db.py-style) since this is exercising
    # genuine DB round-tripping (geocoded_points), not just call wiring.
    from airtag_sentry import tracker as tracker_module

    monkeypatch.setattr(tracker_module, "get_conn", lambda _url: conn)
    monkeypatch.setattr(tracker_module, "is_connected", lambda _cfg: False)  # skip the AirTag session entirely
    monkeypatch.setattr(tracker_module, "fetch_owner_device_locations", lambda _cfg, _conn: [])
    monkeypatch.setattr(tracker_module, "build_notifiers", lambda _cfg, _conn: [])
    monkeypatch.setattr(tracker_module, "build_ha_publisher", lambda _cfg, _conn: None)

    geocode_calls = []

    def fake_reverse_geocode(lat, lon):
        geocode_calls.append((lat, lon))
        return GeocodeResult(address="12 Main St", poi_name="REWE")

    monkeypatch.setattr(tracker_module, "reverse_geocode", fake_reverse_geocode)

    tracker_module._geocode_new_points(conn, [(49.8728, 8.6512), (49.8728, 8.6512)])

    # Same rounded coordinate twice -> one real geocode call, cached after that.
    assert geocode_calls == [(49.8728, 8.6512)]
    assert get_geocoded_point(conn, 49.8728, 8.6512) == GeocodedPoint(
        lat_rounded=49.8728, lon_rounded=8.6512, address="12 Main St", poi_name="REWE"
    )


def test_geocode_new_points_skips_already_cached_coordinates(monkeypatch, conn):
    from airtag_sentry import tracker as tracker_module

    store_geocoded_point(conn, 49.8728, 8.6512, "Cached Address", "Cached POI")

    def fail_if_called(*_a, **_k):
        raise AssertionError("reverse_geocode should not be called for an already-cached coordinate")

    monkeypatch.setattr(tracker_module, "reverse_geocode", fail_if_called)

    tracker_module._geocode_new_points(conn, [(49.8728, 8.6512)])
```

(Add `GeocodedPoint`, `get_geocoded_point`, `store_geocoded_point` to `tests/test_tracker.py`'s import block, and `from airtag_sentry.geocode import GeocodeResult`.)

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_tracker.py -k geocode -v`
Expected: FAIL with `AttributeError: module 'airtag_sentry.tracker' has no attribute '_geocode_new_points'`

- [ ] **Step 4: Implement `_geocode_new_points` and wire it into both poll paths**

Add to `airtag_sentry/tracker.py`'s imports:

```python
from airtag_sentry.db import (
    Alert as DbAlert,
)
from airtag_sentry.db import (
    AirtagRecord,
    AppSettings,
    Report,
    count_reports,
    fetch_reports_before,
    get_airtag_key,
    get_conn,
    get_geocoded_point,
    get_settings,
    insert_reports,
    latest_primary_owner_device_location,
    list_airtags,
    list_owner_devices,
    record_alert,
    record_owner_device_location,
    round_coord,
    store_geocoded_point,
)
from airtag_sentry.geocode import reverse_geocode
from airtag_sentry.movement import MovementConfig, evaluate_away, evaluate_movement
```

Add the helper function (near the top, after `_load_key`):

```python
def _geocode_new_points(conn, points: list[tuple[float, float]]) -> None:
    """Best-effort: geocodes any of `points` not already in geocoded_points,
    deduping by the same ~1m rounding the cache uses so a stay's several
    pings only trigger one real Nominatim call. Runs on the background
    scheduler thread, never blocking the web app - a failed lookup just
    leaves that coordinate ungeocoded until it's seen again."""
    seen: set[tuple[float, float]] = set()
    for lat, lon in points:
        key = round_coord(lat, lon)
        if key in seen:
            continue
        seen.add(key)
        if get_geocoded_point(conn, lat, lon) is not None:
            continue
        try:
            result = reverse_geocode(lat, lon)
        except Exception:
            logger.exception("Reverse geocoding failed for (%s, %s).", lat, lon)
            continue
        if result.address is not None or result.poi_name is not None:
            store_geocoded_point(conn, lat, lon, result.address, result.poi_name)
```

Wire it into `_update_owner_devices` (after the `for location in locations:` loop body currently ending around line 103):

```python
    for location in locations:
        record_owner_device_location(conn, location)
        if ha_publisher is not None:
            device = devices_by_id.get(location.device_id)
            name = (device.display_name or device.name) if device else location.device_id
            try:
                ha_publisher.publish_owner_device(
                    location.device_id,
                    name,
                    location.lat,
                    location.horizontal_accuracy,
                    location.battery_level,
                )
            except Exception:
                logger.exception("Failed to publish owner device '%s' to Home Assistant.", location.device_id)
    _geocode_new_points(conn, [(loc.lat, loc.lon) for loc in locations])
```

Wire it into `_poll_airtag` (right after the `logger.info("[%s] Inserted %d new report(s).", ...)` line, currently line 173):

```python
    logger.info("[%s] Inserted %d new report(s).", airtag.id, len(newly_inserted))
    _geocode_new_points(conn, [(r.lat, r.lon) for r in newly_inserted])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_tracker.py -v`
Expected: PASS (all tests, including pre-existing ones)

- [ ] **Step 6: Run the full backend test suite**

Run: `pytest -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add airtag_sentry/tracker.py tests/test_tracker.py
git commit -m "Geocode newly-polled coordinates in the background poller"
```

---

## Task 6: Places CRUD routes

**Files:**
- Modify: `airtag_sentry/web/app.py`
- Test: `tests/test_web_auth.py`

**Interfaces:**
- Consumes: `list_named_places`, `create_named_place`, `update_named_place`, `delete_named_place` from `airtag_sentry.db` (Task 1).
- Produces: `GET /api/places`, `POST /api/places`, `PUT /api/places/{place_id}`, `DELETE /api/places/{place_id}`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_web_auth.py` (add `NamedPlace` to the `from airtag_sentry.db import (...)` block):

```python
def test_get_places_returns_persisted_places(client, monkeypatch):
    _login(client, monkeypatch)
    monkeypatch.setattr(app_module, "get_conn", lambda _url: contextlib.nullcontext(Mock()))
    monkeypatch.setattr(
        app_module,
        "list_named_places",
        lambda _conn: [NamedPlace(id=1, name="Home", lat=49.87, lon=8.65, radius_meters=75.0)],
    )

    resp = client.get("/api/places")

    assert resp.status_code == 200
    assert resp.json() == [{"id": 1, "name": "Home", "lat": 49.87, "lon": 8.65, "radius_meters": 75.0}]


def test_create_place_rejects_empty_name(client, monkeypatch):
    _login(client, monkeypatch)

    resp = client.post("/api/places", json={"name": "  ", "lat": 0, "lon": 0, "radius_meters": 50})

    assert resp.status_code == 400


def test_create_place_route(client, monkeypatch):
    _login(client, monkeypatch)
    monkeypatch.setattr(app_module, "get_conn", lambda _url: contextlib.nullcontext(Mock()))
    monkeypatch.setattr(
        app_module,
        "create_named_place",
        lambda _conn, name, lat, lon, radius_meters: NamedPlace(
            id=1, name=name, lat=lat, lon=lon, radius_meters=radius_meters
        ),
    )

    resp = client.post("/api/places", json={"name": "Home", "lat": 49.87, "lon": 8.65, "radius_meters": 75.0})

    assert resp.status_code == 200
    assert resp.json() == {"id": 1, "name": "Home", "lat": 49.87, "lon": 8.65, "radius_meters": 75.0}


def test_update_place_route_404s_for_unknown_id(client, monkeypatch):
    _login(client, monkeypatch)
    monkeypatch.setattr(app_module, "get_conn", lambda _url: contextlib.nullcontext(Mock()))
    monkeypatch.setattr(app_module, "update_named_place", lambda *a, **k: None)

    resp = client.put("/api/places/999", json={"name": "Home", "lat": 0, "lon": 0, "radius_meters": 50})

    assert resp.status_code == 404


def test_delete_place_route(client, monkeypatch):
    _login(client, monkeypatch)
    monkeypatch.setattr(app_module, "get_conn", lambda _url: contextlib.nullcontext(Mock()))
    deleted_ids = []
    monkeypatch.setattr(app_module, "delete_named_place", lambda _conn, place_id: deleted_ids.append(place_id))

    resp = client.delete("/api/places/1")

    assert resp.status_code == 200
    assert deleted_ids == [1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web_auth.py -k "place" -v`
Expected: FAIL with 404 (routes don't exist yet)

- [ ] **Step 3: Add the `NamedPlaceIn` model and routes**

Add to `airtag_sentry/web/app.py`'s imports (extend the existing `from airtag_sentry.db import (...)` block alphabetically): `create_named_place`, `delete_named_place`, `list_named_places`, `update_named_place`.

Add the Pydantic model near `SettingsIn` (`airtag_sentry/web/app.py:237-245`):

```python
class NamedPlaceIn(BaseModel):
    name: str
    lat: float
    lon: float
    radius_meters: float = Field(gt=0)
```

Add the routes near the other CRUD groups (e.g. right after the `/api/settings` routes, `airtag_sentry/web/app.py:713-722`):

```python
    @app.get("/api/places")
    def get_places():
        with get_conn(cfg.database_url) as conn:
            places = list_named_places(conn)
        return [dataclasses.asdict(p) for p in places]

    @app.post("/api/places")
    def create_place_route(body: NamedPlaceIn):
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="name must not be empty.")
        with get_conn(cfg.database_url) as conn:
            place = create_named_place(conn, name, body.lat, body.lon, body.radius_meters)
        return dataclasses.asdict(place)

    @app.put("/api/places/{place_id}")
    def update_place_route(place_id: int, body: NamedPlaceIn):
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="name must not be empty.")
        with get_conn(cfg.database_url) as conn:
            place = update_named_place(conn, place_id, name, body.lat, body.lon, body.radius_meters)
            if place is None:
                raise HTTPException(status_code=404, detail="Place not found.")
        return dataclasses.asdict(place)

    @app.delete("/api/places/{place_id}")
    def delete_place_route(place_id: int):
        with get_conn(cfg.database_url) as conn:
            delete_named_place(conn, place_id)
        return {"ok": True}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web_auth.py -k "place" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add airtag_sentry/web/app.py tests/test_web_auth.py
git commit -m "Add Places CRUD routes"
```

---

## Task 7: Geocode correction routes

**Files:**
- Modify: `airtag_sentry/web/app.py`
- Test: `tests/test_web_auth.py`

**Interfaces:**
- Consumes: `set_place_label_correction`, `delete_place_label_correction` from `airtag_sentry.db` (Task 2).
- Produces: `PUT /api/geocode/correction`, `DELETE /api/geocode/correction`.

- [ ] **Step 1: Write the failing tests**

```python
def test_set_geocode_correction_rejects_empty_name(client, monkeypatch):
    _login(client, monkeypatch)

    resp = client.put("/api/geocode/correction", json={"lat": 0, "lon": 0, "corrected_name": "  "})

    assert resp.status_code == 400


def test_set_geocode_correction_route(client, monkeypatch):
    _login(client, monkeypatch)
    monkeypatch.setattr(app_module, "get_conn", lambda _url: contextlib.nullcontext(Mock()))
    calls = []
    monkeypatch.setattr(
        app_module,
        "set_place_label_correction",
        lambda _conn, lat, lon, corrected_name: calls.append((lat, lon, corrected_name)),
    )

    resp = client.put(
        "/api/geocode/correction", json={"lat": 49.87, "lon": 8.65, "corrected_name": "My Store"}
    )

    assert resp.status_code == 200
    assert calls == [(49.87, 8.65, "My Store")]


def test_delete_geocode_correction_route(client, monkeypatch):
    _login(client, monkeypatch)
    monkeypatch.setattr(app_module, "get_conn", lambda _url: contextlib.nullcontext(Mock()))
    calls = []
    monkeypatch.setattr(
        app_module, "delete_place_label_correction", lambda _conn, lat, lon: calls.append((lat, lon))
    )

    resp = client.delete("/api/geocode/correction?lat=49.87&lon=8.65")

    assert resp.status_code == 200
    assert calls == [(49.87, 8.65)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web_auth.py -k "geocode_correction" -v`
Expected: FAIL with 404

- [ ] **Step 3: Add the model and routes**

Add `set_place_label_correction`, `delete_place_label_correction` to `airtag_sentry/web/app.py`'s `from airtag_sentry.db import (...)` block.

Add near `NamedPlaceIn` (Task 6):

```python
class GeocodeCorrectionIn(BaseModel):
    lat: float
    lon: float
    corrected_name: str
```

Add the routes right after the existing `/api/geocode` route (Task 4, Step 6):

```python
    @app.put("/api/geocode/correction")
    def set_geocode_correction_route(body: GeocodeCorrectionIn):
        name = body.corrected_name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="corrected_name must not be empty.")
        with get_conn(cfg.database_url) as conn:
            set_place_label_correction(conn, body.lat, body.lon, name)
        return {"ok": True}

    @app.delete("/api/geocode/correction")
    def delete_geocode_correction_route(lat: float, lon: float):
        with get_conn(cfg.database_url) as conn:
            delete_place_label_correction(conn, lat, lon)
        return {"ok": True}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web_auth.py -k "geocode_correction" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add airtag_sentry/web/app.py tests/test_web_auth.py
git commit -m "Add geocode label correction routes"
```

---

## Task 8: `/api/reports` and `/api/owner-devices/history` return `{raw, stays}`

**Files:**
- Modify: `airtag_sentry/web/app.py`
- Create: `tests/test_web_history.py`

**Interfaces:**
- Consumes: `cluster_by_proximity`, `match_place`, `resolve_label` from `airtag_sentry.stays` (Task 3); `get_geocoded_point`, `get_place_label_correction`, `list_named_places` from `airtag_sentry.db`.
- Produces: `GET /api/reports` now returns `{"raw": [...], "stays": [{"anchor_id", "start", "end", "count", "lat", "lon", "label", "place_id"}, ...]}`; `GET /api/owner-devices/history` now returns the same shape with `"anchor_recorded_at"` instead of `"anchor_id"`.

- [ ] **Step 1: Write the failing tests**

This task tests genuine integration across `stays.py` + `db.py` + the route, so it uses a real Postgres connection (test_db.py's `conn` fixture pattern) rather than mocking every db call - create `tests/test_web_history.py`:

```python
import contextlib
import datetime as dt
import os
import time
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import psycopg
import pytest
from fastapi.testclient import TestClient

from airtag_sentry.config import load_config
from airtag_sentry.db import (
    OwnerLocation,
    Report,
    create_airtag,
    create_named_place,
    get_conn,
    insert_reports,
    record_owner_device_location,
    set_place_label_correction,
    store_geocoded_point,
    upgrade_to_head,
    upsert_owner_devices,
)
from airtag_sentry.web import app as app_module

TEST_DATABASE_URL = os.environ.setdefault(
    "TEST_DATABASE_URL", "postgresql://airtag:airtag@localhost:5432/airtag_sentry_test"
)


@pytest.fixture()
def conn():
    try:
        with get_conn(TEST_DATABASE_URL) as connection:
            upgrade_to_head()
            with connection.cursor() as cur:
                cur.execute(
                    "TRUNCATE airtags, location_reports, owner_devices, owner_device_locations, "
                    "named_places, geocoded_points, place_label_corrections RESTART IDENTITY CASCADE"
                )
            connection.commit()
            create_airtag(connection, "bike", "Fahrrad")
            yield connection
    except psycopg.OperationalError:
        pytest.skip(f"Postgres not reachable at {TEST_DATABASE_URL}; start it to run this test.")


@pytest.fixture()
def cfg(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "airtag")
    monkeypatch.setenv("POSTGRES_PASSWORD", "change-me")
    monkeypatch.setenv("POSTGRES_DB", "airtag_sentry")
    monkeypatch.setenv("OIDC_ISSUER", "https://authentik.example.com/application/o/airtag-sentry/")
    monkeypatch.setenv("OIDC_CLIENT_ID", "client-id")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("OIDC_ALLOWED_USERNAME", "octocat")
    monkeypatch.setenv("SESSION_SECRET_KEY", "session-secret")
    monkeypatch.setenv("AIRTAG_KEY_ENCRYPTION_KEY", "PTx2A3nrHR9wKR_hqK0YtxHZgHqEeZOo8VvV3XwZjxA=")
    return load_config()


@pytest.fixture()
def client(cfg, conn, monkeypatch):
    app = app_module.create_app(cfg)
    monkeypatch.setattr(app_module, "get_conn", lambda _url: contextlib.nullcontext(conn))
    # Real OIDC discovery is lazy - pre-seed it (see test_web_auth.py's
    # identical fixture) so _login below can drive a real /auth/login ->
    # /auth/callback round trip without hitting the network.
    app.state.oauth.authentik.server_metadata.update(
        {
            "issuer": "https://authentik.example.com/application/o/airtag-sentry/",
            "authorization_endpoint": "https://authentik.example.com/application/o/authorize/",
            "token_endpoint": "https://authentik.example.com/application/o/token/",
            "userinfo_endpoint": "https://authentik.example.com/application/o/userinfo/",
            "_loaded_at": time.time(),
        }
    )
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


def _login(client, monkeypatch):
    """Drives a real login round-trip so AuthMiddleware accepts subsequent
    requests - same approach as test_web_auth.py's identical helper
    (duplicated rather than imported: tests/ has no __init__.py, so
    cross-module test imports aren't a stable pattern here)."""
    authentik = client.app.state.oauth.authentik
    monkeypatch.setattr(
        authentik, "fetch_access_token", AsyncMock(return_value={"access_token": "tok", "token_type": "Bearer"})
    )
    monkeypatch.setattr(authentik, "userinfo", AsyncMock(return_value={"preferred_username": "octocat"}))

    login_resp = client.get("/auth/login")
    state = parse_qs(urlparse(login_resp.headers["location"]).query)["state"][0]
    client.get(f"/auth/callback?code=abc&state={state}")


def test_reports_route_returns_raw_points_and_a_labeled_stay(client, conn, monkeypatch):
    _login(client, monkeypatch)
    reports = [
        Report(
            id=None, airtag_id="bike", timestamp=dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc),
            lat=49.8728, lon=8.6512, accuracy=5.0, confidence=3, battery_level="full",
        ),
        Report(
            id=None, airtag_id="bike", timestamp=dt.datetime(2026, 1, 1, 13, 0, tzinfo=dt.timezone.utc),
            lat=49.8728, lon=8.6512, accuracy=5.0, confidence=3, battery_level="full",
        ),
    ]
    insert_reports(conn, reports)
    create_named_place(conn, "Home", 49.8728, 8.6512, 50.0)

    resp = client.get("/api/reports?airtag_id=bike")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["raw"]) == 2
    assert len(body["stays"]) == 1
    stay = body["stays"][0]
    assert stay["count"] == 2
    assert stay["label"] == "Home"
    assert stay["place_id"] is not None
    assert stay["start"] == "2026-01-01T12:00:00+00:00"
    assert stay["end"] == "2026-01-01T13:00:00+00:00"


def test_reports_route_falls_back_to_correction_then_poi_then_address(client, conn, monkeypatch):
    _login(client, monkeypatch)
    insert_reports(
        conn,
        [
            Report(
                id=None, airtag_id="bike", timestamp=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
                lat=49.8728, lon=8.6512, accuracy=None, confidence=None, battery_level=None,
            )
        ],
    )
    store_geocoded_point(conn, 49.8728, 8.6512, "12 Main St", "REWE")

    resp = client.get("/api/reports?airtag_id=bike")
    assert resp.json()["stays"][0]["label"] == "REWE"

    set_place_label_correction(conn, 49.8728, 8.6512, "My Corner Store")
    resp = client.get("/api/reports?airtag_id=bike")
    assert resp.json()["stays"][0]["label"] == "My Corner Store"


def test_owner_device_history_route_returns_raw_points_and_a_labeled_stay(client, conn, monkeypatch):
    _login(client, monkeypatch)
    upsert_owner_devices(conn, [{"id": "d1", "name": "iPhone", "device_type": "iPhone"}], dt.datetime.now(dt.timezone.utc))
    record_owner_device_location(
        conn,
        OwnerLocation(
            id=None, device_id="d1", recorded_at=dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc),
            lat=49.8728, lon=8.6512, horizontal_accuracy=5.0,
        ),
    )
    create_named_place(conn, "Home", 49.8728, 8.6512, 50.0)

    resp = client.get("/api/owner-devices/history?device_id=d1")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["raw"]) == 1
    assert body["stays"][0]["label"] == "Home"
    assert body["stays"][0]["anchor_recorded_at"] == "2026-01-01T12:00:00+00:00"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web_history.py -v`
Expected: FAIL - `body["raw"]`/`body["stays"]` `KeyError`, since the routes still return a bare list.

- [ ] **Step 3: Implement the label-resolution helper and update both routes**

Add to `airtag_sentry/web/app.py`'s imports: `cluster_by_proximity`, `match_place`, `resolve_label` from `airtag_sentry.stays`; `get_geocoded_point`, `get_place_label_correction` from `airtag_sentry.db` (already importing `list_named_places` from Task 6).

Add a module-level helper next to `_slugify` (`airtag_sentry/web/app.py:325`) - it needs no `cfg`/`create_app` closure, just a connection and plain values:

```python
def _stay_label(conn, place, lat: float, lon: float) -> str | None:
    correction = get_place_label_correction(conn, lat, lon)
    geocoded = get_geocoded_point(conn, lat, lon)
    return resolve_label(
        place,
        correction,
        geocoded.poi_name if geocoded else None,
        geocoded.address if geocoded else None,
    )
```

Replace the `/api/reports` route body (`airtag_sentry/web/app.py:666-679`):

```python
    @app.get("/api/reports")
    def get_reports(airtag_id: str | None = None, limit: int | None = None):
        with get_conn(cfg.database_url) as conn:
            resolved = _resolve_airtag_id(conn, airtag_id)
            reports = fetch_reports(conn, resolved, limit=limit)
            radius = get_settings(conn).history_cluster_radius_meters
            places = list_named_places(conn)
            clusters = cluster_by_proximity(reports, lambda r: (r.lat, r.lon), radius)
            stays = []
            for c in clusters:
                place = match_place(c.anchor.lat, c.anchor.lon, places)
                stays.append(
                    {
                        "anchor_id": c.anchor.id,
                        "start": c.points[0].timestamp.isoformat(),
                        "end": c.points[-1].timestamp.isoformat(),
                        "count": len(c.points),
                        "lat": c.anchor.lat,
                        "lon": c.anchor.lon,
                        "label": _stay_label(conn, place, c.anchor.lat, c.anchor.lon),
                        "place_id": place.id if place else None,
                    }
                )
        return {
            "raw": [
                {
                    "id": r.id,
                    "timestamp": r.timestamp.isoformat(),
                    "lat": r.lat,
                    "lon": r.lon,
                    "accuracy": r.accuracy,
                    "confidence": r.confidence,
                    "battery_level": r.battery_level,
                }
                for r in reports
            ],
            "stays": stays,
        }
```

Replace the `/api/owner-devices/history` route body (`airtag_sentry/web/app.py:850-866`):

```python
    @app.get("/api/owner-devices/history")
    def get_owner_device_history(device_id: str, limit: int = 200):
        """History of one owner device's location, newest first, plus its
        computed stays. device_id is a query param, not a path segment - see
        OwnerDeviceEnabledIn for why."""
        with get_conn(cfg.database_url) as conn:
            locations = fetch_owner_device_location_history(conn, device_id, limit=limit)
            radius = get_settings(conn).history_cluster_radius_meters
            places = list_named_places(conn)
            clusters = cluster_by_proximity(locations, lambda l: (l.lat, l.lon), radius)
            stays = []
            for c in clusters:
                place = match_place(c.anchor.lat, c.anchor.lon, places)
                # locations (and so c.points) are newest-first - the latest
                # point in a stay is the first one encountered, the earliest
                # the last (see CLAUDE.md's Report/OwnerLocation asymmetry).
                stays.append(
                    {
                        "anchor_recorded_at": c.anchor.recorded_at.isoformat(),
                        "start": c.points[-1].recorded_at.isoformat(),
                        "end": c.points[0].recorded_at.isoformat(),
                        "count": len(c.points),
                        "lat": c.anchor.lat,
                        "lon": c.anchor.lon,
                        "label": _stay_label(conn, place, c.anchor.lat, c.anchor.lon),
                        "place_id": place.id if place else None,
                    }
                )
        return {
            "raw": [
                {
                    "recorded_at": loc.recorded_at.isoformat(),
                    "lat": loc.lat,
                    "lon": loc.lon,
                    "horizontal_accuracy": loc.horizontal_accuracy,
                    "battery_level": loc.battery_level,
                    "battery_status": loc.battery_status,
                }
                for loc in locations
            ],
            "stays": stays,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web_history.py -v`
Expected: PASS

- [ ] **Step 5: Run the full backend test suite**

Run: `pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add airtag_sentry/web/app.py tests/test_web_history.py
git commit -m "Return labeled stays alongside raw points from the history routes"
```

---

## Task 9: Frontend `api.ts` - new types and calls

**Files:**
- Modify: `frontend/src/api.ts`

**Interfaces:**
- Produces: `ReportStay`, `LocationStay`, `ReportHistory`, `LocationHistory`, `Place` types; `getReports(airtagId, limit?) -> Promise<ReportHistory>` (return type changes); `getOwnerDeviceHistory(id, limit?) -> Promise<LocationHistory>` (return type changes); `getPlaces() -> Promise<Place[]>`; `createPlace(input) -> Promise<Place>`; `updatePlace(id, input) -> Promise<Place>`; `deletePlace(id) -> Promise<void>`; `setGeocodeCorrection(lat, lon, correctedName) -> Promise<void>`; `clearGeocodeCorrection(lat, lon) -> Promise<void>`.

- [ ] **Step 1: Add the new types**

Add after the `Report` interface (`frontend/src/api.ts:9-19`):

```ts
export interface ReportStay {
  anchor_id: number
  start: string
  end: string
  count: number
  lat: number
  lon: number
  label: string | null
  place_id: number | null
}

export interface ReportHistory {
  raw: Report[]
  stays: ReportStay[]
}
```

Add after the `OwnerLocation` interface (`frontend/src/api.ts:60-76`):

```ts
export interface LocationStay {
  anchor_recorded_at: string
  start: string
  end: string
  count: number
  lat: number
  lon: number
  label: string | null
  place_id: number | null
}

export interface LocationHistory {
  raw: OwnerLocation[]
  stays: LocationStay[]
}
```

Add near the end of the file (alongside the other simple entity types):

```ts
export interface Place {
  id: number
  name: string
  lat: number
  lon: number
  radius_meters: number
}
```

- [ ] **Step 2: Change `getReports`/`getOwnerDeviceHistory` return types**

Replace (`frontend/src/api.ts:160-164`):

```ts
export async function getReports(airtagId: string, limit = 500): Promise<ReportHistory> {
  return (
    await apiFetch(`/api/reports?airtag_id=${encodeURIComponent(airtagId)}&limit=${limit}`)
  ).json()
}
```

Replace (`frontend/src/api.ts:242-248`):

```ts
export async function getOwnerDeviceHistory(id: string, limit = 200): Promise<LocationHistory> {
  return (
    await apiFetch(
      `/api/owner-devices/history?device_id=${encodeURIComponent(id)}&limit=${limit}`,
    )
  ).json()
}
```

- [ ] **Step 3: Add Places CRUD and correction calls**

Add near the end of the file:

```ts
export async function getPlaces(): Promise<Place[]> {
  return (await apiFetch('/api/places')).json()
}

export async function createPlace(input: {
  name: string
  lat: number
  lon: number
  radius_meters: number
}): Promise<Place> {
  return (await apiFetch('/api/places', { method: 'POST', body: JSON.stringify(input) })).json()
}

export async function updatePlace(
  id: number,
  input: { name: string; lat: number; lon: number; radius_meters: number },
): Promise<Place> {
  return (
    await apiFetch(`/api/places/${id}`, { method: 'PUT', body: JSON.stringify(input) })
  ).json()
}

export async function deletePlace(id: number): Promise<void> {
  await apiFetch(`/api/places/${id}`, { method: 'DELETE' })
}

export async function setGeocodeCorrection(
  lat: number,
  lon: number,
  correctedName: string,
): Promise<void> {
  await apiFetch('/api/geocode/correction', {
    method: 'PUT',
    body: JSON.stringify({ lat, lon, corrected_name: correctedName }),
  })
}

export async function clearGeocodeCorrection(lat: number, lon: number): Promise<void> {
  await apiFetch(`/api/geocode/correction?lat=${lat}&lon=${lon}`, { method: 'DELETE' })
}
```

- [ ] **Step 4: Type-check**

Run: `cd frontend && npx tsc -b`
Expected: FAILS - `App.tsx` still destructures `getReports`/`getOwnerDeviceHistory` results as bare arrays. This is expected; Task 10 fixes it. Confirm the *only* errors are in `App.tsx` (not `api.ts` itself), to isolate this task's own correctness.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api.ts
git commit -m "api.ts: add Stay/Place types, update history fetch return shapes"
```

---

## Task 10: `App.tsx` rework - remove client clustering, fetch stays/places

**Files:**
- Delete: `frontend/src/clustering.ts`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `ReportHistory`, `LocationHistory`, `ReportStay`, `LocationStay`, `Place`, `getPlaces` from `api.ts` (Task 9).
- Produces: new App.tsx state `reportStays: ReportStay[]`, `ownerLocationStays: Record<string, LocationStay[]>`, `places: Place[]`; stepper (`stepOlder`/`stepNewer`/`stepPosition`) now operates on stays directly, no client-side clustering.
- Removed: the `settings`/`refreshSettings` state and effect added for client-side `clusterRadiusMeters` (no longer needed - clustering is server-side now); the `clusterByProximity` import.

- [ ] **Step 1: Delete `clustering.ts`**

```bash
git rm frontend/src/clustering.ts
```

- [ ] **Step 2: Remove the settings-for-clustering state**

In `frontend/src/App.tsx`, remove the `AppSettings` import, the `settings`/`setSettings` state block (added for `history_cluster_radius_meters`), its `refreshSettings` callback and mount effect, its `refreshSettings` reference in the auto-refresh `tick()` function and that `useEffect`'s dependency array, the `clusterRadiusMeters` derived variable, and the `import { clusterByProximity } from './clustering'` line. `SettingsPanel.tsx` already fetches `AppSettings` independently for its own Tracking page - this was App-level state added solely to feed the (now server-side) clustering radius to `MapCard`/`DeviceMapCard`/`AirtagDetail`/`DeviceDetail`, all of which stop taking that prop as part of this task and Task 11/12.

- [ ] **Step 3: Add `reportStays`, `ownerLocationStays`, `places` state**

Add near the existing `reports`/`ownerLocationHistories` state:

```ts
  const [reportStays, setReportStays] = useState<ReportStay[]>([])
  // Keyed by device_id, mirroring ownerLocationHistories.
  const [ownerLocationStays, setOwnerLocationStays] = useState<Record<string, LocationStay[]>>({})
  const [places, setPlaces] = useState<Place[]>([])
```

Add `ReportStay`, `LocationStay`, `Place`, `getPlaces` to the existing `import type { ... } from './api'` / `import { ... } from './api'` statements.

- [ ] **Step 4: Update `refreshReports` to destructure `{raw, stays}`**

Replace:

```ts
  const refreshReports = useCallback(async () => {
    const id = currentId
    if (!id) {
      setReports([])
      setReportStays([])
      return
    }
    const { raw, stays } = await getReports(id)
    if (currentIdRef.current === id) {
      setReports(raw)
      setReportStays(stays)
    }
  }, [currentId])
```

- [ ] **Step 5: Update `refreshOwnerDevices` to destructure `{raw, stays}` per device**

Replace the `entries`/`setOwnerLocationHistories` block at the end of `refreshOwnerDevices`:

```ts
    const entries = await Promise.all(
      enabled.map((d) =>
        getOwnerDeviceHistory(d.id)
          .then((h) => [d.id, h] as const)
          .catch(() => [d.id, { raw: [], stays: [] }] as const),
      ),
    )
    setOwnerLocationHistories(Object.fromEntries(entries.map(([id, h]) => [id, h.raw])))
    setOwnerLocationStays(Object.fromEntries(entries.map(([id, h]) => [id, h.stays])))
```

- [ ] **Step 6: Add `refreshPlaces` and wire it into the mount effect + auto-refresh tick**

```ts
  const refreshPlaces = useCallback(async () => {
    await getPlaces()
      .then(setPlaces)
      .catch(() => {})
  }, [])

  useEffect(() => {
    refreshPlaces()
  }, [refreshPlaces])
```

Add `refreshPlaces()` to the `tick()` function and `refreshPlaces` to that `useEffect`'s dependency array (the same auto-refresh block `refreshSettings` was removed from in Step 2).

- [ ] **Step 7: Rewrite the stepper block to operate on stays directly**

Replace the entire "Older/newer navigation" block:

```ts
  // Older/newer navigation, shared by the mobile title bar's stepper below
  // and the desktop sidebar's HistoryStepper (AirtagDetail.tsx/
  // DeviceDetail.tsx) - moved here from the map popup, see tasks/todo.md.
  // Steps stay-to-stay - reportStays/ownerLocationStays are already computed
  // server-side (see stays.py), so this is a plain array walk, no clustering
  // here anymore. AirTag stays arrive oldest-first, owner-device stays
  // newest-first (see CLAUDE.md), so "older"/"newer" step in opposite index
  // directions for each; mirrored from the same logic MapCard.tsx/
  // DeviceMapCard.tsx use to pick their displayed stay.
  let stepOlder: (() => void) | null = null
  let stepNewer: (() => void) | null = null
  // "Steps back from the latest stay" (1 = latest), counted the same way
  // regardless of which array direction the underlying data arrives in -
  // HistoryStepper just renders whatever count it's given, see the comment
  // there.
  let stepPosition: { current: number; total: number } | null = null
  if (detail === 'airtag' && currentAirtag) {
    const selectedIndex =
      selectedReportId != null ? reportStays.findIndex((s) => s.anchor_id === selectedReportId) : -1
    const displayedIndex = selectedIndex >= 0 ? selectedIndex : reportStays.length - 1
    const older = displayedIndex > 0 ? reportStays[displayedIndex - 1] : null
    const newer = displayedIndex < reportStays.length - 1 ? reportStays[displayedIndex + 1] : null
    if (older) stepOlder = () => setSelectedReportId(older.anchor_id)
    if (newer) stepNewer = () => setSelectedReportId(newer.anchor_id)
    if (reportStays.length > 0) {
      stepPosition = { current: reportStays.length - displayedIndex, total: reportStays.length }
    }
  } else if (detail === 'device' && selectedDevice) {
    const stays = ownerLocationStays[selectedDevice.id] ?? []
    const selectedIndex =
      selectedDeviceLocationKey != null
        ? stays.findIndex((s) => s.anchor_recorded_at === selectedDeviceLocationKey)
        : -1
    const displayedIndex = selectedIndex >= 0 ? selectedIndex : 0
    const older = displayedIndex < stays.length - 1 ? stays[displayedIndex + 1] : null
    const newer = displayedIndex > 0 ? stays[displayedIndex - 1] : null
    if (older) stepOlder = () => setSelectedDeviceLocationKey(older.anchor_recorded_at)
    if (newer) stepNewer = () => setSelectedDeviceLocationKey(newer.anchor_recorded_at)
    if (stays.length > 0) stepPosition = { current: displayedIndex + 1, total: stays.length }
  }
```

- [ ] **Step 8: Update the `MapCard`/`DeviceMapCard`/`AirtagDetail`/`DeviceDetail` JSX call sites**

Replace `clusterRadiusMeters={clusterRadiusMeters}` with `stays={reportStays}` and `places={places}` on `<MapCard>`; with `stays={ownerLocationStays[selectedDevice.id] ?? []}` and `places={places}` on `<DeviceMapCard>` (Task 11 defines these props - `?? []` is fine here, `DeviceMapCard` has no "still loading" state, just "no positions yet"). Remove the `reports={reports}` prop from the `<AirtagDetail>` call site entirely and replace `historyClusterRadiusMeters={clusterRadiusMeters}` with `stays={reportStays}` (Task 12 removes the now-unused `reports` prop from `AirtagDetail`'s own `Props`). Remove the `history={ownerLocationHistories[selectedDevice.id] ?? null}` prop from the `<DeviceDetail>` call site entirely and replace `historyClusterRadiusMeters={clusterRadiusMeters}` with `stays={ownerLocationStays[selectedDevice.id] ?? null}` - **keep the `?? null`** (not `?? []`): `DeviceDetail`'s history panel distinguishes "still loading" (`null`, shows "Lädt…") from "loaded, empty" (`[]`), the same distinction its removed `history` prop made.

- [ ] **Step 9: Type-check**

Run: `cd frontend && npx tsc -b`
Expected: FAILS - `MapCard`/`DeviceMapCard`/`AirtagDetail`/`DeviceDetail` don't accept `stays`/`places` props yet. Confirm the errors are confined to those four components' prop types (Tasks 11/12 fix them), not to `App.tsx` itself.

- [ ] **Step 10: Commit**

```bash
git add -A frontend/src/App.tsx frontend/src/clustering.ts
git commit -m "App.tsx: fetch server-computed stays/places, remove client-side clustering"
```

---

## Task 11: `MapCard.tsx`/`DeviceMapCard.tsx` rework

**Files:**
- Modify: `frontend/src/components/MapCard.tsx`
- Modify: `frontend/src/components/DeviceMapCard.tsx`
- Modify: `frontend/src/mapIcons.ts`

**Interfaces:**
- Consumes: `ReportStay`, `LocationStay`, `Place` from `api.ts`; `formatClusterRange` from `format.ts` (already exists).
- Produces: `MapCard` and `DeviceMapCard` take `stays`/`places` props instead of `clusterRadiusMeters`; new exported `PlaceCircles` component (in `MapCard.tsx`, imported by `DeviceMapCard.tsx`); `HistoryPoints` gains an optional `getRadius` prop; `SelectedPin` gains an optional `label` prop; `useCurrentPosition` becomes exported (needed by `SettingsPlaces.tsx` in Task 13).

- [ ] **Step 1: Add `PLACE_CIRCLE_COLOR` to `mapIcons.ts`**

Add next to `OWNER_TRAIL_COLOR` (`frontend/src/mapIcons.ts:144`):

```ts
export const PLACE_CIRCLE_COLOR = '#30d158'
```

- [ ] **Step 2: Export `useCurrentPosition`**

In `frontend/src/components/MapCard.tsx`, change `function useCurrentPosition()` (currently line 81) to `export function useCurrentPosition()`.

- [ ] **Step 3: Add a radius-scaling helper and thread it through `HistoryPoints`**

Add near the top of `MapCard.tsx` (after the imports):

```ts
/** A stay's marker grows (mildly, clamped) with how long it lasted - a
 * 10-minute stop and an 8-hour stay should read differently on the map at a
 * glance, matching how Google Timeline treats visit significance. */
export function stayMarkerRadius(count: number): number {
  return Math.min(6 + Math.sqrt(count) * 1.5, 16)
}
```

Update `HistoryPoints`' signature and body (currently lines 162-204) to accept an optional `getRadius`:

```ts
export function HistoryPoints<T extends { lat: number; lon: number }>({
  points,
  displayedIndex,
  color,
  getKey,
  getRadius,
  onSelect,
}: {
  points: T[]
  displayedIndex: number
  color: string
  getKey: (point: T, index: number) => string | number
  getRadius?: (point: T) => number
  onSelect?: (point: T) => void
}) {
  return (
    <>
      {points.map((point, i) =>
        i === displayedIndex ? null : (
          <CircleMarker
            key={getKey(point, i)}
            center={[point.lat, point.lon]}
            radius={getRadius ? getRadius(point) : 6}
            pathOptions={{ color: '#fff', weight: 2, fillColor: color, fillOpacity: 0.9, opacity: 0.9 }}
            eventHandlers={
              onSelect
                ? {
                    click: (e) => {
                      DomEvent.stopPropagation(e)
                      onSelect(point)
                    },
                  }
                : undefined
            }
          />
        ),
      )}
    </>
  )
}
```

(Only the new `getRadius` prop and the `radius={getRadius ? getRadius(point) : 6}` line change - the rest of the function body, including the click-stop-propagation comment, is unchanged.)

- [ ] **Step 4: Add a `label` prop to `SelectedPin` for the permanent on-map name tooltip**

Update `SelectedPin`'s signature and body (currently lines 230-264):

```ts
export function SelectedPin({
  position,
  icon,
  label,
  children,
}: {
  position: [number, number]
  icon: L.DivIcon
  // Permanent on-map name (e.g. a matched geofence's name) - shown above the
  // pin without needing a click, unlike the rest of the popup content.
  label?: string | null
  children: ReactNode
}) {
  const map = useMap()
  const popupRef = useRef<L.Popup>(null)
  const [lat, lon] = position
  useEffect(() => {
    popupRef.current?.openOn(map)
  }, [map, lat, lon])
  return (
    <>
      <Marker
        position={position}
        icon={icon}
        eventHandlers={{
          click: (e) => {
            centerMarkerOnClick(e)
            popupRef.current?.openOn(map)
          },
        }}
      >
        {label && (
          <Tooltip permanent direction="top" offset={[0, -SIZE]} className="!border-none !bg-transparent !shadow-none !p-0">
            <span className="rounded-full bg-[var(--surface)] px-2 py-0.5 text-[0.7rem] font-medium text-[var(--text)] shadow">
              {label}
            </span>
          </Tooltip>
        )}
      </Marker>
      {/* autoPan off: centerMarkerOnClick above already centers this pin
          explicitly on click. */}
      <Popup ref={popupRef} position={position} offset={PIN_POPUP_OFFSET} autoPan={false}>
        {children}
      </Popup>
    </>
  )
}
```

This references `SIZE`, the pin icon size constant already defined in `mapIcons.ts` (used by `airtagPinIcon`) - import it into `MapCard.tsx`: add `SIZE` to the existing `import { ... } from '../mapIcons'` line. (Check `mapIcons.ts` - if `SIZE` isn't exported yet, add `export` to its existing `const SIZE = ...` declaration.)

Add `Tooltip` to the existing `import { CircleMarker, MapContainer, TileLayer, Polyline, Marker, Popup, useMap, useMapEvent } from 'react-leaflet'` line.

- [ ] **Step 5: Add the `PlaceCircles` component**

Add near `HistoryPoints` in `MapCard.tsx`:

```tsx
/** Read-only translucent geofence overlays - the editable version (drag to
 * move/resize) only exists in SettingsPlaces.tsx's editor. Exported for
 * DeviceMapCard.tsx, which shares this same rendering (see CLAUDE.md's
 * AirTag/device parity constraint). */
export function PlaceCircles({ places }: { places: { id: number; name: string; lat: number; lon: number; radius_meters: number }[] }) {
  return (
    <>
      {places.map((p) => (
        <Circle
          key={p.id}
          center={[p.lat, p.lon]}
          radius={p.radius_meters}
          pathOptions={{ color: PLACE_CIRCLE_COLOR, weight: 2, fillColor: PLACE_CIRCLE_COLOR, fillOpacity: 0.1 }}
        />
      ))}
    </>
  )
}
```

Add `Circle` to the react-leaflet import line, and `PLACE_CIRCLE_COLOR` to the `import { ... } from '../mapIcons'` line.

- [ ] **Step 6: Rework `MapCard`'s body to render from `stays`/`places` instead of client-computed clusters**

Replace the `MapCard` function's props and body (currently lines 313-478) with:

```tsx
export function MapCard({
  reports,
  stays,
  airtag,
  places = [],
  ownerLocations = [],
  ownerLocationHistories = {},
  onSelectDevice,
  selectedReportId = null,
  onSelectReport,
  onMapClick,
}: {
  reports: Report[]
  // Server-computed (see stays.py / GET /api/reports) - already deduped,
  // labeled (geofence/correction/POI/address priority), and time-ranged.
  stays: ReportStay[]
  airtag: Airtag
  places?: Place[]
  ownerLocations?: OwnerLocation[]
  ownerLocationHistories?: Record<string, OwnerLocation[]>
  onSelectDevice?: (id: string) => void
  selectedReportId?: number | null
  onSelectReport?: (id: number) => void
  onMapClick?: () => void
}) {
  const positions = useMemo<[number, number][]>(() => reports.map((r) => [r.lat, r.lon]), [reports])
  const selectedIndex = selectedReportId != null ? stays.findIndex((s) => s.anchor_id === selectedReportId) : -1
  const displayedIndex = selectedIndex >= 0 ? selectedIndex : stays.length - 1
  const displayed = stays[displayedIndex] as ReportStay | undefined
  const displayedPosition = useMemo<[number, number]>(
    () => [displayed?.lat ?? 0, displayed?.lon ?? 0],
    [displayed?.lat, displayed?.lon],
  )
  const animatedPosition = useAnimatedLatLng(displayedPosition)

  if (positions.length === 0 || !displayed) {
    return <NoReportsView onMapClick={onMapClick} />
  }

  const last = positions[positions.length - 1]
  const trailColor = deviceColor(airtag)

  return (
    <MapContainer center={last} zoom={15} className="h-full w-full">
      <TileLayer
        attribution="&copy; OpenStreetMap contributors"
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <Polyline positions={positions} pathOptions={{ color: trailColor, weight: 4 }} />
      <PlaceCircles places={places} />
      <HistoryPoints
        points={stays}
        displayedIndex={displayedIndex}
        color={trailColor}
        getKey={(s) => s.anchor_id}
        getRadius={(s) => stayMarkerRadius(s.count)}
        onSelect={onSelectReport ? (s) => onSelectReport(s.anchor_id) : undefined}
      />
      {Object.entries(ownerLocationHistories).map(([deviceId, history]) => {
        const ownerPositions: [number, number][] = history.map((l) => [l.lat, l.lon])
        if (ownerPositions.length < 2) return null
        return (
          <Polyline
            key={deviceId}
            positions={ownerPositions}
            pathOptions={{ color: OWNER_TRAIL_COLOR, weight: 3, dashArray: '6 6' }}
          />
        )
      })}
      <SelectedPin position={animatedPosition} icon={airtagPinIcon(airtag)} label={displayed.label}>
        <div className={POPUP_WIDTH_CLASS}>
          <p className="mb-2 text-[0.95rem] font-semibold">
            {selectedIndex >= 0 ? 'Ausgewählte Position' : 'Letzte Position'}
          </p>
          <InfoRow icon={<ClockIcon className="h-3.5 w-3.5" />}>
            {displayed.count > 1
              ? `${formatClusterRange(displayed.start, displayed.end)} · ${displayed.count}×`
              : new Date(displayed.start).toLocaleString()}
          </InfoRow>
          {displayed.label && (
            <InfoRow icon={<MapPinIcon className="h-3.5 w-3.5" />}>{displayed.label}</InfoRow>
          )}
          <a
            href={mapsUrl(displayedPosition[0], displayedPosition[1], airtag.name)}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 flex items-center justify-center gap-1.5 rounded-lg border border-[var(--accent)] px-3 py-1.5 text-xs font-medium text-[var(--accent)]"
          >
            <LocationArrowIcon className="h-3.5 w-3.5" />
            In Karten öffnen
          </a>
        </div>
      </SelectedPin>
      {ownerLocations.map((loc) => (
        <Marker
          key={loc.device_id}
          position={[loc.lat, loc.lon]}
          icon={airtagPinIcon({ id: loc.device_id, icon: loc.icon, color: loc.color })}
          eventHandlers={{ click: centerMarkerOnClick }}
        >
          <Popup autoPan={false}>
            <div className={POPUP_WIDTH_CLASS}>
              <p className="mb-2 text-[0.95rem] font-semibold">{loc.name ?? 'Gerät'}</p>
              <InfoRow icon={<ClockIcon className="h-3.5 w-3.5" />}>
                {capitalize(formatRelative(loc.recorded_at))}
              </InfoRow>
              {onSelectDevice && (
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => onSelectDevice(loc.device_id)}
                    className="rounded-lg bg-[var(--accent)] px-2.5 py-1.5 text-xs font-medium text-white"
                  >
                    Details anzeigen
                  </button>
                  <a
                    href={mapsUrl(loc.lat, loc.lon, loc.name ?? 'Gerät')}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-lg border border-[var(--accent)] px-2.5 py-1.5 text-xs font-medium text-[var(--accent)]"
                  >
                    <LocationArrowIcon className="h-3.5 w-3.5" />
                    In Karten öffnen
                  </a>
                </div>
              )}
            </div>
          </Popup>
        </Marker>
      ))}
      <FitBounds positions={positions} />
      <PanToSelection position={displayedPosition} />
      <InvalidateSizeOnResize />
      <MapClickHandler onMapClick={onMapClick} />
    </MapContainer>
  )
}
```

Add `ReportStay`, `Place` to the `import type { Airtag, OwnerLocation, Report } from '../api'` line. Remove the now-unused `import { clusterByProximity } from '../clustering'` line and `getAddress` import if `AddressLine` no longer needs it here - **do not remove `AddressLine` itself**, it's still used by `NoReportsView` (unchanged, below in the same file).

- [ ] **Step 7: Type-check just this file's shape**

Run: `cd frontend && npx tsc -b`
Expected: Errors should now be confined to `DeviceMapCard.tsx` (Step 8 below fixes it) - confirm `MapCard.tsx` itself has none.

- [ ] **Step 8: Rework `DeviceMapCard.tsx` to mirror `MapCard.tsx` exactly**

Replace `frontend/src/components/DeviceMapCard.tsx` entirely with:

```tsx
import { useMemo } from 'react'
import { MapContainer, TileLayer, Polyline } from 'react-leaflet'
import type { LocationStay, OwnerDevice, Place } from '../api'
import { deviceLabel, formatClusterRange } from '../format'
import { useAnimatedLatLng } from '../hooks/useAnimatedLatLng'
import { airtagPinIcon, deviceColor } from '../mapIcons'
import { mapsUrl } from '../maps'
import {
  FitBounds,
  HistoryPoints,
  InfoRow,
  InvalidateSizeOnResize,
  MapClickHandler,
  NoReportsView,
  PanToSelection,
  PlaceCircles,
  POPUP_WIDTH_CLASS,
  SelectedPin,
  stayMarkerRadius,
} from './MapCard'
import { ClockIcon, LocationArrowIcon, MapPinIcon } from './icons'

/** Single-device counterpart to MapCard - one owner device's own location
 * trail, drilled into from ObjectsList (device selected -> DeviceDetail).
 * Reuses MapCard's map primitives instead of duplicating them; solid trail
 * (vs. the dashed one OverviewMap/MapCard draw for every *other* tracked
 * device in the background) since this is the one thing being looked at.
 * Selection/prev-next/address behavior mirrors MapCard.tsx exactly - AirTags
 * and owner devices get the same map navigation features (see CLAUDE.md). */
export function DeviceMapCard({
  device,
  locations,
  stays,
  places = [],
  selectedLocationKey = null,
  onSelectLocation,
  onMapClick,
}: {
  device: OwnerDevice
  locations: OwnerLocation[]
  // Server-computed (see stays.py / GET /api/owner-devices/history).
  stays: LocationStay[]
  places?: Place[]
  selectedLocationKey?: string | null
  onSelectLocation?: (recordedAt: string) => void
  onMapClick?: () => void
}) {
  const positions = useMemo<[number, number][]>(() => locations.map((l) => [l.lat, l.lon]), [locations])

  const selectedIndex =
    selectedLocationKey != null ? stays.findIndex((s) => s.anchor_recorded_at === selectedLocationKey) : -1
  const displayedIndex = selectedIndex >= 0 ? selectedIndex : 0
  const displayed = stays[displayedIndex] as LocationStay | undefined
  const displayedPosition = useMemo<[number, number]>(
    () => [displayed?.lat ?? 0, displayed?.lon ?? 0],
    [displayed?.lat, displayed?.lon],
  )
  const animatedPosition = useAnimatedLatLng(displayedPosition)

  if (positions.length === 0 || !displayed) {
    return <NoReportsView onMapClick={onMapClick} />
  }

  const trailColor = deviceColor(device)

  return (
    <MapContainer center={displayedPosition} zoom={15} className="h-full w-full">
      <TileLayer
        attribution="&copy; OpenStreetMap contributors"
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {positions.length > 1 && (
        <Polyline positions={positions} pathOptions={{ color: trailColor, weight: 4 }} />
      )}
      <PlaceCircles places={places} />
      <HistoryPoints
        points={stays}
        displayedIndex={displayedIndex}
        color={trailColor}
        getKey={(s) => s.anchor_recorded_at}
        getRadius={(s) => stayMarkerRadius(s.count)}
        onSelect={onSelectLocation ? (s) => onSelectLocation(s.anchor_recorded_at) : undefined}
      />
      <SelectedPin position={animatedPosition} icon={airtagPinIcon(device)} label={displayed.label}>
        <div className={POPUP_WIDTH_CLASS}>
          <p className="mb-2 text-[0.95rem] font-semibold">{deviceLabel(device)}</p>
          <InfoRow icon={<ClockIcon className="h-3.5 w-3.5" />}>
            {displayed.count > 1
              ? `${formatClusterRange(displayed.start, displayed.end)} · ${displayed.count}×`
              : new Date(displayed.start).toLocaleString()}
          </InfoRow>
          {displayed.label && (
            <InfoRow icon={<MapPinIcon className="h-3.5 w-3.5" />}>{displayed.label}</InfoRow>
          )}
          <a
            href={mapsUrl(displayedPosition[0], displayedPosition[1], deviceLabel(device))}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 flex items-center justify-center gap-1.5 rounded-lg border border-[var(--accent)] px-3 py-1.5 text-xs font-medium text-[var(--accent)]"
          >
            <LocationArrowIcon className="h-3.5 w-3.5" />
            In Karten öffnen
          </a>
        </div>
      </SelectedPin>
      <FitBounds positions={positions} />
      <PanToSelection position={displayedPosition} />
      <InvalidateSizeOnResize />
      <MapClickHandler onMapClick={onMapClick} />
    </MapContainer>
  )
}
```

Note: `OwnerLocation` is used only as the `locations` prop's element type - add `import type { OwnerLocation } from '../api'` alongside the `LocationStay, OwnerDevice, Place` import. `AddressLine`/`getAddress` are deliberately absent from this file now - the popup's label comes from `displayed.label` (already resolved server-side), so this file never needs a live geocode call; `MapCard.tsx`'s own `NoReportsView` still uses `AddressLine` internally for its unrelated browser-geolocation fallback (Task 11 Step 6), untouched by this change.

- [ ] **Step 9: Type-check and build**

Run: `cd frontend && npx tsc -b`
Expected: Errors should now be confined to `App.tsx`'s `<AirtagDetail>`/`<DeviceDetail>` call sites (Task 12) and `AirtagDetail.tsx`/`DeviceDetail.tsx` themselves - confirm `MapCard.tsx`/`DeviceMapCard.tsx` have none.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components/MapCard.tsx frontend/src/components/DeviceMapCard.tsx frontend/src/mapIcons.ts
git commit -m "MapCard/DeviceMapCard: render server-computed stays and geofence overlays"
```

---

## Task 12: `HistoryList`/`DeviceHistoryList` rework + correction UI

**Files:**
- Modify: `frontend/src/components/AirtagDetail.tsx`
- Modify: `frontend/src/components/DeviceDetail.tsx`

**Interfaces:**
- Consumes: `ReportStay`, `LocationStay` from `api.ts`; `StayRow` from the new `StayRow.tsx` (this task).
- Produces: `AirtagDetail`/`DeviceDetail` take a `stays` prop instead of `reports: Report[]`/`history: OwnerLocation[] | null` and `historyClusterRadiusMeters`; `HistoryList`/`DeviceHistoryList` render stays directly with an inline correction affordance.

- [ ] **Step 1: Update `AirtagDetail.tsx`'s `Props` and destructuring**

`reports` was only ever used for `HistoryList` and the "Verlauf" row's count badge - both now read `stays` instead, so `reports` is removed from `Props` entirely rather than kept alongside `stays` (App.tsx's `<MapCard>` still needs raw `reports` for its trail polyline, but that's a separate prop on a separate component - unaffected).

Replace `reports: Report[]` and `historyClusterRadiusMeters: number` in the `Props` interface with:

```ts
  // Server-computed (see stays.py / GET /api/reports).
  stays: ReportStay[]
```

Replace `reports,` and `historyClusterRadiusMeters,` in the `AirtagDetail({...})` destructuring with `stays,`.

Update the `<HistoryList>` call site:

```tsx
            {historyOpen && (
              <HistoryList stays={stays} selectedReportId={selectedReportId} onSelectReport={onSelectReport} />
            )}
```

Update the `Verlauf` row's count badge from `{reports.length}` to `{stays.length}`.

Update the file's imports:
- `import type { Airtag, Report, Status } from '../api'` becomes `import type { Airtag, ReportStay, Status } from '../api'` (`Report` is no longer referenced anywhere in this file once `reports` is gone).
- Remove `import { clusterByProximity } from '../clustering'` entirely (only `HistoryList` used it).
- Change `import { useEffect, useMemo, useRef, useState } from 'react'` to `import { useEffect, useRef, useState } from 'react'` (`useMemo` was only used by the old `HistoryList`'s `rows` computation, which the rewrite below no longer needs).
- Change the `format.ts` import from `import { capitalize, formatAirtagBattery, formatAlertReason, formatClusterRange, formatRelative, isLowBattery } from '../format'` to `import { formatAirtagBattery, formatAlertReason, formatRelative, isLowBattery } from '../format'` - `capitalize` and `formatClusterRange` were only used inside the old `HistoryList`'s row rendering (moving into `StayRow.tsx`, Step 3); `formatRelative`/`formatAirtagBattery`/`formatAlertReason`/`isLowBattery` are still used elsewhere in this file (the "Zuletzt gesehen"/battery/alert lines) and stay.
- `PencilIcon` stays imported - it's still used by the unrelated "Umbenennen" row.

- [ ] **Step 2: Rewrite `HistoryList`**

Replace the entire `HistoryList` function:

```tsx
function HistoryList({
  stays,
  selectedReportId,
  onSelectReport,
}: {
  stays: ReportStay[]
  selectedReportId: number | null
  onSelectReport: (id: number) => void
}) {
  // Newest first for display - stays arrive in the same oldest-first order
  // as the underlying reports (see stays.py).
  const rows = [...stays].reverse()
  const rowRefs = useRef(new Map<number, HTMLButtonElement>())
  useEffect(() => {
    if (selectedReportId == null) return
    rowRefs.current.get(selectedReportId)?.scrollIntoView({ block: 'nearest' })
  }, [selectedReportId])

  if (rows.length === 0) {
    return (
      <div className="border-t border-[var(--divider)] p-4 text-center text-sm text-[var(--text-secondary)]">
        Noch keine Reports vorhanden.
      </div>
    )
  }
  return (
    <div className="max-h-80 overflow-y-auto border-t border-[var(--divider)]">
      {rows.map((s, i) => (
        <StayRow
          key={s.anchor_id}
          rowRef={(el) => {
            if (el) rowRefs.current.set(s.anchor_id, el)
            else rowRefs.current.delete(s.anchor_id)
          }}
          stay={s}
          bordered={i > 0}
          selected={s.anchor_id === selectedReportId}
          onSelect={() => onSelectReport(s.anchor_id)}
        />
      ))}
    </div>
  )
}
```

`HistoryList` now renders `<StayRow>`, defined in its own shared file next (`DeviceDetail.tsx` needs the identical component - parity constraint - so it's not defined inline in either file).

- [ ] **Step 3: Create the shared `StayRow` component**

`frontend/src/components/StayRow.tsx`:

```tsx
import { useState } from 'react'
import { setGeocodeCorrection } from '../api'
import { capitalize, formatClusterRange, formatRelative } from '../format'
import { PencilIcon } from './icons'

/** One history row - shared shape for a single ping or a multi-ping stay,
 * with an inline "correct this label" affordance. Generic over ReportStay/
 * LocationStay (both carry the same {start, end, count, lat, lon, label}
 * fields) so AirtagDetail.tsx and DeviceDetail.tsx render identically (see
 * CLAUDE.md's parity constraint) despite their different anchor-key types. */
export function StayRow({
  stay,
  rowRef,
  bordered,
  selected,
  onSelect,
}: {
  stay: { start: string; end: string; count: number; lat: number; lon: number; label: string | null }
  rowRef: (el: HTMLButtonElement | null) => void
  bordered: boolean
  selected: boolean
  onSelect: () => void
}) {
  const [correcting, setCorrecting] = useState(false)
  const [correctionInput, setCorrectionInput] = useState(stay.label ?? '')
  const [saving, setSaving] = useState(false)

  async function saveCorrection() {
    const trimmed = correctionInput.trim()
    if (!trimmed) return
    setSaving(true)
    try {
      await setGeocodeCorrection(stay.lat, stay.lon, trimmed)
      setCorrecting(false)
    } finally {
      setSaving(false)
    }
  }

  if (correcting) {
    return (
      <div className={`flex items-center gap-2 px-4 py-2 text-sm ${bordered ? 'border-t border-[var(--divider)]' : ''}`}>
        <input
          autoFocus
          value={correctionInput}
          onChange={(e) => setCorrectionInput(e.target.value)}
          placeholder="Name für diesen Ort"
          className="min-w-0 flex-1 rounded-lg border border-[var(--divider)] bg-[var(--surface-2)] px-2 py-1 text-sm outline-none focus:border-[var(--accent)]"
        />
        <button type="button" onClick={saveCorrection} disabled={saving} className="text-[var(--accent)]">
          Sichern
        </button>
        <button type="button" onClick={() => setCorrecting(false)} className="text-[var(--text-secondary)]">
          Abbrechen
        </button>
      </div>
    )
  }

  const isStay = stay.count > 1
  return (
    <button
      type="button"
      ref={rowRef}
      onClick={onSelect}
      title={
        isStay
          ? `${new Date(stay.start).toLocaleString()} – ${new Date(stay.end).toLocaleString()}`
          : new Date(stay.start).toLocaleString()
      }
      className={`group flex w-full items-center justify-between px-4 py-2 text-left text-sm ${bordered ? 'border-t border-[var(--divider)]' : ''} ${
        selected ? 'bg-[var(--accent)]/15' : 'hover:bg-white/5'
      }`}
    >
      <span className="flex items-center gap-1.5">
        {isStay ? formatClusterRange(stay.start, stay.end) : capitalize(formatRelative(stay.start))}
        <span
          onClick={(e) => {
            e.stopPropagation()
            setCorrecting(true)
          }}
        >
          <PencilIcon className="h-3 w-3 shrink-0 text-[var(--text-secondary)] opacity-0 group-hover:opacity-100" />
        </span>
      </span>
      <span className="text-[var(--text-secondary)]">
        {isStay && `${stay.count}× · `}
        {stay.label ?? `${stay.lat.toFixed(4)}, ${stay.lon.toFixed(4)}`}
      </span>
    </button>
  )
}
```

In `AirtagDetail.tsx`, replace the in-file `StayRow` definition from Step 2 with `import { StayRow } from './StayRow'`, and drop the now-unused `capitalize`/`formatClusterRange`/`formatRelative`/`setGeocodeCorrection`/`PencilIcon` imports/usages that moved into `StayRow.tsx` (keep whichever of these `AirtagDetail.tsx` still uses elsewhere in the file, e.g. `formatRelative` for the "Zuletzt gesehen" line - check before removing).

- [ ] **Step 4: Mirror in `DeviceDetail.tsx`**

`history: OwnerLocation[] | null` was only used for `DeviceHistoryList` and the "Verlauf" row's count badge - both now read `stays` instead, so `history` is removed from `Props` entirely (mirroring `AirtagDetail.tsx`'s `reports` removal in Step 1). `location: OwnerLocation | null` (the *singular* current-position prop driving the header's "Zuletzt gesehen"/battery display) is a separate, unrelated prop and stays untouched.

Replace `history: OwnerLocation[] | null` and `historyClusterRadiusMeters: number` in `DeviceDetail`'s `Props` with:

```ts
  // Server-computed (see stays.py / GET /api/owner-devices/history). null
  // while still loading (see App.tsx's `?? null`), distinct from `[]` (no
  // history yet) - DeviceHistoryList shows "Lädt…" only for the former.
  stays: LocationStay[] | null
```

Replace `history,` and `historyClusterRadiusMeters,` in the `DeviceDetail({...})` destructuring with `stays,`.

Update the `<DeviceHistoryList>` call site:

```tsx
            {historyOpen && (
              <DeviceHistoryList
                stays={stays}
                selectedLocationKey={selectedLocationKey}
                onSelectLocation={onSelectLocation}
              />
            )}
```

Update the "Verlauf" row's count badge from `{history?.length ?? ''}` to `{stays?.length ?? ''}`.

Update the file's imports:
- `import { useEffect, useMemo, useRef, useState } from 'react'` becomes `import { useEffect, useRef, useState } from 'react'` (`useMemo` was only used by the old `DeviceHistoryRows`' `clusters` computation).
- Remove `import { clusterByProximity } from '../clustering'` entirely.
- Change `import { capitalize, deviceLabel, formatClusterRange, formatDeviceBattery, formatRelative, isLowBattery } from '../format'` to `import { deviceLabel, formatDeviceBattery, formatRelative, isLowBattery } from '../format'` - `capitalize` and `formatClusterRange` were only used inside the old `DeviceHistoryRows`' row rendering (now in `StayRow.tsx`, Step 3); `formatRelative` is still used by the header's "Zuletzt gesehen" line and stays.
- Add `import { StayRow } from './StayRow'` and add `LocationStay` to the `import type { OwnerDevice, OwnerLocation } from '../api'` line (`OwnerLocation` itself stays - the `location: OwnerLocation | null` prop still needs it).

Replace `DeviceHistoryList`/`DeviceHistoryRows` with:

```tsx
function DeviceHistoryList({
  stays,
  selectedLocationKey,
  onSelectLocation,
}: {
  stays: LocationStay[] | null
  selectedLocationKey: string | null
  onSelectLocation: (recordedAt: string) => void
}) {
  if (stays === null) {
    return (
      <div className="border-t border-[var(--divider)] p-4 text-center text-sm text-[var(--text-secondary)]">
        Lädt…
      </div>
    )
  }
  if (stays.length === 0) {
    return (
      <div className="border-t border-[var(--divider)] p-4 text-center text-sm text-[var(--text-secondary)]">
        Noch kein Standortverlauf vorhanden.
      </div>
    )
  }
  return <DeviceHistoryRows stays={stays} selectedLocationKey={selectedLocationKey} onSelectLocation={onSelectLocation} />
}

function DeviceHistoryRows({
  stays,
  selectedLocationKey,
  onSelectLocation,
}: {
  stays: LocationStay[]
  selectedLocationKey: string | null
  onSelectLocation: (recordedAt: string) => void
}) {
  const rowRefs = useRef(new Map<string, HTMLButtonElement>())
  useEffect(() => {
    if (selectedLocationKey == null) return
    rowRefs.current.get(selectedLocationKey)?.scrollIntoView({ block: 'nearest' })
  }, [selectedLocationKey])

  // Already newest-first (see stays.py / GET /api/owner-devices/history) -
  // no reversal needed here, same as before.
  return (
    <div className="max-h-80 overflow-y-auto border-t border-[var(--divider)]">
      {stays.map((s, i) => (
        <StayRow
          key={s.anchor_recorded_at}
          rowRef={(el) => {
            if (el) rowRefs.current.set(s.anchor_recorded_at, el)
            else rowRefs.current.delete(s.anchor_recorded_at)
          }}
          stay={s}
          bordered={i > 0}
          selected={s.anchor_recorded_at === selectedLocationKey}
          onSelect={() => onSelectLocation(s.anchor_recorded_at)}
        />
      ))}
    </div>
  )
}
```

- [ ] **Step 5: Type-check and build**

Run: `cd frontend && npx tsc -b`
Expected: PASS - Task 10 Step 8 already updated `App.tsx`'s `<AirtagDetail>`/`<DeviceDetail>` call sites to match these new `Props` shapes.

Run: `cd frontend && npx vite build`
Expected: PASS

Run: `cd frontend && npx oxlint`
Expected: No new warnings beyond the four pre-existing `set-state-in-effect` ones already present before this plan.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/AirtagDetail.tsx frontend/src/components/DeviceDetail.tsx frontend/src/components/StayRow.tsx
git commit -m "HistoryList/DeviceHistoryList: render server-computed stays with inline label correction"
```

---

## Task 13: `SettingsPlaces.tsx` - geofence management with drag-to-edit circle

**Files:**
- Create: `frontend/src/components/EditableCircle.tsx`
- Create: `frontend/src/components/SettingsPlaces.tsx`
- Modify: `frontend/src/components/SettingsPanel.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/package.json`

**Interfaces:**
- Consumes: `Place`, `createPlace`, `updatePlace`, `deletePlace` from `api.ts`; `useCurrentPosition` from `MapCard.tsx` (exported in Task 11).
- Produces: `SettingsPlaces` component; `SettingsPanel` gains `places`/`onPlacesChanged` props.

- [ ] **Step 1: Add the `leaflet-geoman-free` dependency**

```bash
cd frontend && npm install @geoman-io/leaflet-geoman-free
```

Verify `frontend/package.json`'s `dependencies` now includes `"@geoman-io/leaflet-geoman-free": "^2.18.0"` (or whatever current version `npm install` resolved - check `package.json` after the install rather than hand-editing the version).

- [ ] **Step 2: Write `EditableCircle.tsx`**

```tsx
import { useEffect, useRef } from 'react'
import L from 'leaflet'
import '@geoman-io/leaflet-geoman-free'
import { useMap } from 'react-leaflet'
import { PLACE_CIRCLE_COLOR } from '../mapIcons'

/** leaflet-geoman augments L.Circle.prototype with `.pm` via its side-effect
 * import above - @types/leaflet has no knowledge of it, so this narrow cast
 * is the only place that needs to know the augmented shape exists. */
type GeomanCircle = L.Circle & { pm: { enable: (options?: Record<string, unknown>) => void } }

/**
 * An imperative Leaflet Circle (not a declarative react-leaflet `<Circle>`)
 * with leaflet-geoman's drag-to-move-center / drag-to-resize-radius editing
 * enabled - there's no react-leaflet prop API for geoman's editing, so this
 * mounts a real L.Circle once and only ever reads/writes it imperatively.
 * `center`/`radius` props seed the *initial* geometry only; after that the
 * circle itself is the source of truth, mirrored back to the caller via
 * `onChange` whenever geoman fires an edit event - see
 * https://geoman.io/docs/leaflet/modes/edit-mode for the exact event names
 * (`pm:edit` during a drag, `pm:markerdragend` when a handle drag finishes).
 */
export function EditableCircle({
  center,
  radius,
  onChange,
}: {
  center: [number, number]
  radius: number
  onChange: (center: [number, number], radius: number) => void
}) {
  const map = useMap()
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  useEffect(() => {
    const circle = L.circle(center, {
      radius,
      color: PLACE_CIRCLE_COLOR,
      fillColor: PLACE_CIRCLE_COLOR,
      fillOpacity: 0.15,
      weight: 2,
    }).addTo(map) as GeomanCircle

    function sync() {
      const latlng = circle.getLatLng()
      onChangeRef.current([latlng.lat, latlng.lng], circle.getRadius())
    }
    circle.on('pm:edit', sync)
    circle.on('pm:markerdragend', sync)
    circle.pm.enable({ draggable: true })

    return () => {
      circle.off('pm:edit', sync)
      circle.off('pm:markerdragend', sync)
      circle.remove()
    }
    // Mount once - the circle layer is the source of truth after that;
    // re-running this for every `center`/`radius` prop change (e.g. from the
    // very `onChange` calls this effect fires) would fight the user's
    // in-progress drag by recreating the layer under their cursor.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map])

  return null
}
```

- [ ] **Step 3: Write `SettingsPlaces.tsx`**

```tsx
import { useState } from 'react'
import { MapContainer, TileLayer } from 'react-leaflet'
import type { Place } from '../api'
import { createPlace, deletePlace, updatePlace } from '../api'
import { Row, Section } from './AirtagDetail'
import { EditableCircle } from './EditableCircle'
import { ChevronRightIcon, MapPinIcon, PlusIcon, TrashIcon } from './icons'
import { useCurrentPosition } from './MapCard'

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
```

- [ ] **Step 4: Wire `SettingsPlaces` into `SettingsPanel.tsx`**

Add `'places'` to the `Page` union (`frontend/src/components/SettingsPanel.tsx:82`).

Add `places: Place[]` and `onPlacesChanged: () => void | Promise<void>` to `Props` (same file, `:84-89`), and destructure them in `SettingsPanel({...})`.

Add a `page === 'places'` branch (alongside the existing `page === 'tracking'` branch):

```tsx
  if (page === 'places') {
    return (
      <div className="flex h-full flex-col">
        <BackHeader title="Orte" onBack={() => setPage('root')} />
        <div className="flex-1 overflow-y-auto pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-2">
          <SettingsPlaces places={places} onChanged={onPlacesChanged} />
        </div>
      </div>
    )
  }
```

Add a navigation `Row` in the root page's `Section` (alongside "Tracking"):

```tsx
            <Row
              icon={<MapPinIcon className="h-5 w-5" />}
              label="Orte"
              trailing={<ChevronRightIcon className="h-4 w-4 text-[var(--text-secondary)]" />}
              onClick={() => setPage('places')}
            />
```

Add `import { SettingsPlaces } from './SettingsPlaces'`, `MapPinIcon` to the icons import, and `Place` to the `import type { AppSettings } from '../api'` line.

- [ ] **Step 5: Thread `places`/`refreshPlaces` from `App.tsx` into `SettingsPanel`**

In `frontend/src/App.tsx`, add `places={places}` and `onPlacesChanged={refreshPlaces}` to the existing `<SettingsPanel>` call site.

- [ ] **Step 6: Type-check, build, and lint**

Run: `cd frontend && npx tsc -b`
Expected: PASS

Run: `cd frontend && npx vite build`
Expected: PASS

Run: `cd frontend && npx oxlint`
Expected: No new warnings beyond the four pre-existing `set-state-in-effect` ones.

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/components/EditableCircle.tsx frontend/src/components/SettingsPlaces.tsx frontend/src/components/SettingsPanel.tsx frontend/src/App.tsx
git commit -m "Add Places settings screen with drag-to-edit geofence circle"
```

---

## Task 14: Full-stack verification pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend test suite against a real Postgres**

```bash
docker run -d --rm --name airtag_sentry_pg_verify -e POSTGRES_USER=airtag -e POSTGRES_PASSWORD=airtag -e POSTGRES_DB=airtag_sentry_test -p 5433:5432 postgres:17-alpine
# wait for pg_isready, then:
TEST_DATABASE_URL="postgresql://airtag:airtag@localhost:5433/airtag_sentry_test" pytest -v
docker stop airtag_sentry_pg_verify
```

Expected: all tests PASS, including every test added across Tasks 1-8.

- [ ] **Step 2: Frontend verification**

```bash
cd frontend && npx tsc -b && npx vite build && npx oxlint
```

Expected: `tsc`/`vite build` PASS with no errors; `oxlint` shows no new warnings beyond the four pre-existing `set-state-in-effect` ones.

- [ ] **Step 3: `docker compose config` with a throwaway `.env`**

```bash
cp .env.example .env && docker compose config >/dev/null && rm .env
```

Expected: exits 0.

- [ ] **Step 4: Manual browser check**

Start the app (`docker compose up` or local dev servers) and verify by hand:
- A device with a real multi-ping stay shows a size-scaled marker, a permanent name tooltip if labeled, and the correct time-range/count in both the popup and the list row.
- Creating a geofence in Settings → Orte (drag center, drag edge to resize, name, save) makes it show up as a translucent circle on that device's map, and any of its stays inside the circle immediately show the geofence's name as their label - no manual re-tagging needed, confirming the "previous stays automatically reference it" requirement.
- Editing a label's correction (pencil icon on a list row) persists and is reflected after the next refresh.
- Both an AirTag and an owner device show identical behavior for all of the above (parity constraint).

- [ ] **Step 5: Update `tasks/lessons.md` if anything surprising came up during implementation**

Only if applicable - not a scripted step.
