import datetime as dt
import xml.etree.ElementTree as ET

from airtag_sentry.db import OwnerLocation, Report
from airtag_sentry.export import (
    owner_locations_to_csv,
    points_to_gpx,
    reports_to_csv,
    safe_filename_part,
)


def test_safe_filename_part_strips_unsafe_characters_and_falls_back():
    assert safe_filename_part("  Mein Fahrrad (2026)! ") == "Mein-Fahrrad-2026"
    assert safe_filename_part("../etc/passwd") == "etc-passwd"
    assert safe_filename_part("...", fallback="device") == "device"


def test_csv_export_neutralizes_formula_injection_prefixes():
    ts = dt.datetime(2026, 3, 1, 12, 0, tzinfo=dt.timezone.utc)
    reports = [
        Report(id=1, airtag_id="bike", timestamp=ts, lat=52.5, lon=13.4, accuracy=5.0, confidence=3, battery_level="=CMD()"),
        Report(id=2, airtag_id="bike", timestamp=ts, lat=52.5, lon=13.4, accuracy=5.0, confidence=3, battery_level="+1+1"),
        Report(id=3, airtag_id="bike", timestamp=ts, lat=52.5, lon=13.4, accuracy=5.0, confidence=3, battery_level="-1+1"),
        Report(id=4, airtag_id="bike", timestamp=ts, lat=52.5, lon=13.4, accuracy=5.0, confidence=3, battery_level="@SUM(A1)"),
    ]
    csv_text = reports_to_csv(reports)
    lines = csv_text.strip().splitlines()
    assert lines[1].endswith(",'=CMD()")
    assert lines[2].endswith(",'+1+1")
    assert lines[3].endswith(",'-1+1")
    assert lines[4].endswith(",'@SUM(A1)")

    locs = [
        OwnerLocation(
            id=1,
            device_id="mac-1",
            recorded_at=ts,
            lat=52.5,
            lon=13.4,
            horizontal_accuracy=5.0,
            battery_level=0.9,
            battery_status="=HYPERLINK()",
            battery_reported=True,
        )
    ]
    loc_lines = owner_locations_to_csv(locs).strip().splitlines()
    assert ",'=HYPERLINK()," in loc_lines[1]


def test_points_to_gpx_sorts_chronologically_and_escapes_xml():
    t_late = dt.datetime(2026, 3, 1, 15, 0, tzinfo=dt.timezone.utc)
    t_early = dt.datetime(2026, 3, 1, 9, 0, tzinfo=dt.timezone.utc)
    t_mid = dt.datetime(2026, 3, 1, 12, 0, tzinfo=dt.timezone.utc)

    gpx_text = points_to_gpx(
        "Bike & <Tag>",
        [(t_late, 52.53, 13.43), (t_early, 52.51, 13.41), (t_mid, 52.52, 13.42)],
    )
    root = ET.fromstring(gpx_text)
    ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
    assert root.find("gpx:trk/gpx:name", ns).text == "Bike & <Tag>"
    times = [el.text for el in root.findall("gpx:trk/gpx:trkseg/gpx:trkpt/gpx:time", ns)]
    assert times == ["2026-03-01T09:00:00Z", "2026-03-01T12:00:00Z", "2026-03-01T15:00:00Z"]
