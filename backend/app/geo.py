"""
Geo helpers.

Distance filtering uses plain Haversine math so it works on any Postgres
(including a bare Supabase project with no extensions enabled) and even on
SQLite for local testing -- no PostGIS required for an MVP at city scale.
If this grows past a few hundred thousand rows, swap the Python-side filter
below for a PostGIS `ST_DWithin` query (needs the postgis extension enabled
on the database) for speed.

Hex aggregation uses Uber's H3 library (h3-py) -- the same indexing system
the frontend uses via h3-js, so a cell index computed here lines up exactly
with one computed in the browser.
"""
import math

import h3


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bounding_box(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    """Cheap pre-filter box (min_lat, max_lat, min_lng, max_lng) to use in a
    SQL WHERE clause before the precise Haversine check -- keeps the DB from
    scanning rows nowhere near the point of interest."""
    dlat = radius_km / 111.32
    dlng = radius_km / (111.32 * max(math.cos(math.radians(lat)), 0.01))
    return lat - dlat, lat + dlat, lng - dlng, lng + dlng


def cell_for_point(lat: float, lng: float, resolution: int) -> str:
    return h3.latlng_to_cell(lat, lng, resolution)


def cell_center(h3_index: str) -> tuple[float, float]:
    lat, lng = h3.cell_to_latlng(h3_index)
    return lat, lng


def cell_boundary(h3_index: str) -> list[list[float]]:
    """Returns [[lat,lng], ...] -- ready to hand straight to a Leaflet/deck.gl polygon."""
    return [[lat, lng] for lat, lng in h3.cell_to_boundary(h3_index)]
