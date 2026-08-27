"""
Place search for the map's search box -- addresses, cities, ZIPs, AND
landmarks/business names (e.g. "Central Park, New York" or "Starbucks,
Austin TX"). Returns several ranked candidates rather than committing to
just one, since a short query like "Main St" is genuinely ambiguous.

Uses OpenStreetMap's Nominatim (nominatim.openstreetmap.org) -- free, no API
key, and unlike the Census Geocoder (see app/census.py, still used for the
county-lookup /chat tool -- that one only understands structured addresses,
not place names) Nominatim indexes real-world points of interest too.

Trade-off worth knowing: Nominatim's public instance has a documented usage
policy (roughly 1 request/second, no heavy automated use) meant for exactly
this kind of light, interactive search-box traffic -- not bulk geocoding. A
descriptive User-Agent identifying the app is required by that policy (see
https://operations.osmfoundation.org/policies/nominatim/) -- don't strip it.
If this app ever gets heavy traffic, self-host Nominatim or switch to a paid
provider (Mapbox, Geoapify) instead.

Results are cached in memory per (query, bias) pair; a broken or slow
Nominatim degrades to an empty list rather than a 500 for the rest of the app.
"""
import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "ChaosTrackerApp/1.0 (hobby incident-tracking map; contact via GitHub issues)"

_search_cache: dict[tuple, list[dict]] = {}


def search_places(query: str, limit: int = 6, near: tuple[float, float] | None = None) -> list[dict]:
    """`near`, if given, is (lat, lng) of the current map center -- used to
    bias (not strictly filter) results toward that area via Nominatim's
    viewbox param, so searching "Starbucks" while looking at Manhattan
    favors Manhattan locations over ones on the other side of the country."""
    query = query.strip()
    if not query:
        return []

    near_key = (round(near[0], 2), round(near[1], 2)) if near else None
    key = (query.lower(), limit, near_key)
    if key in _search_cache:
        return _search_cache[key]

    params = {"q": query, "format": "jsonv2", "limit": limit, "addressdetails": 0}
    if near:
        lat, lng = near
        span = 0.35  # roughly a 25-30 mile box -- wide enough to bias, not so wide it stops mattering
        params["viewbox"] = f"{lng - span},{lat + span},{lng + span},{lat - span}"
        params["bounded"] = 0  # bias toward the box, but still fall back to global matches if nothing's nearby

    try:
        resp = httpx.get(NOMINATIM_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=6.0)
        resp.raise_for_status()
        rows = resp.json()
        results = [
            {"label": row["display_name"], "lat": float(row["lat"]), "lng": float(row["lon"])}
            for row in rows
            if "lat" in row and "lon" in row
        ]
    except Exception as e:
        # Degrade to an empty list rather than a 500 (see module docstring),
        # but still log it -- a silent failure here is invisible in the UI
        # (looks identical to "no results found") and was hard to tell apart
        # from a genuinely-unmatched address until logged. In particular,
        # Nominatim returns 429 (visible via resp.raise_for_status() ->
        # httpx.HTTPStatusError) if its ~1 req/sec usage policy is exceeded,
        # which blocks EVERY geocode call -- including normal map search and
        # Add Chaos pin placement -- until the block clears. See
        # app/discovery.py's _geocode_first callers for why that policy
        # matters here: a burst of rapid sequential geocode calls (e.g. AI
        # event/news discovery processing several items in a tight loop) is
        # exactly what can trigger it.
        print(f"[places.search_places] Nominatim request failed for query={query!r}: {type(e).__name__}: {e}")
        results = []

    _search_cache[key] = results
    return results
