"""CSV and GPX location history export helpers for AirTags and owner devices."""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
import xml.etree.ElementTree as ET
from typing import Sequence

from airtag_sentry.db import OwnerLocation, Report

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_SAFE_SLUG_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def safe_filename_part(raw: str, fallback: str = "history") -> str:
    """Normalizes an AirTag/device name into an HTTP-header-safe filename stem."""
    cleaned = _SAFE_SLUG_RE.sub("-", raw.strip()).strip("-._")
    return cleaned[:64] or fallback


def _csv_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        return value.astimezone(dt.timezone.utc).isoformat()
    text = str(value)
    if text.startswith(_FORMULA_PREFIXES):
        return f"'{text}"
    return text


def reports_to_csv(reports: Sequence[Report]) -> str:
    """Renders AirTag location reports as UTF-8 CSV (newest-first or caller order)."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["timestamp", "lat", "lon", "accuracy", "confidence", "battery_level"])
    for r in reports:
        writer.writerow(
            [
                _csv_cell(r.timestamp),
                r.lat,
                r.lon,
                "" if r.accuracy is None else r.accuracy,
                "" if r.confidence is None else r.confidence,
                _csv_cell(r.battery_level),
            ]
        )
    return buf.getvalue()


def owner_locations_to_csv(locations: Sequence[OwnerLocation]) -> str:
    """Renders owner-device location history as UTF-8 CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(
        ["timestamp", "lat", "lon", "horizontal_accuracy", "battery_level", "battery_status", "battery_reported"]
    )
    for loc in locations:
        writer.writerow(
            [
                _csv_cell(loc.recorded_at),
                loc.lat,
                loc.lon,
                "" if loc.horizontal_accuracy is None else loc.horizontal_accuracy,
                "" if loc.battery_level is None else loc.battery_level,
                _csv_cell(loc.battery_status),
                "true" if loc.battery_reported else "false",
            ]
        )
    return buf.getvalue()


def _format_gpx_time(ts: dt.datetime) -> str:
    utc = ts.astimezone(dt.timezone.utc) if ts.tzinfo else ts.replace(tzinfo=dt.timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def points_to_gpx(name: str, points: Sequence[tuple[dt.datetime, float, float]]) -> str:
    """Renders a chronological GPX 1.1 track (<trk>) from (timestamp, lat, lon) points."""
    gpx = ET.Element(
        "gpx",
        {
            "version": "1.1",
            "creator": "AirTagSentry",
            "xmlns": "http://www.topografix.com/GPX/1/1",
        },
    )
    trk = ET.SubElement(gpx, "trk")
    trk_name = ET.SubElement(trk, "name")
    trk_name.text = name
    trkseg = ET.SubElement(trk, "trkseg")
    for ts, lat, lon in sorted(points, key=lambda p: p[0]):
        trkpt = ET.SubElement(trkseg, "trkpt", {"lat": f"{lat:.7f}", "lon": f"{lon:.7f}"})
        time_el = ET.SubElement(trkpt, "time")
        time_el.text = _format_gpx_time(ts)

    ET.indent(gpx, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(gpx, encoding="unicode") + "\n"
