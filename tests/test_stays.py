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
