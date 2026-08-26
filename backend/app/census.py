"""
County-level migration data via two free Census Bureau APIs:

1. The Geocoder (no key needed) -- turns a lat/lng into a county FIPS code.
   https://geocoding.geo.census.gov/geocoder/

2. The ACS Migration Flows API (free key, instant signup) -- reports how many
   people moved into vs. out of a county in the most recent published year.
   https://www.census.gov/data/developers/data-sets/acs-migration-flows.html
   Get a key: https://api.census.gov/data/key_signup.html

This WAS live-tested (2026-08-25) against real Census data for New York
County. That test surfaced a real quirk worth documenting: for the plain
`for=county:X&in=state:Y` query shape used below, Census returns a populated
MOVEDIN on every row but `null` for MOVEDOUT and MOVEDNET on every row, for
every geography this was tried against. MOVEDIN/MOVEDOUT are genuinely
"inbound"/"outbound" (confirmed against Census's own variable labels, in case
you're wondering whether the names are swapped) -- outbound just isn't
published at this query granularity/vintage. Rather than silently reporting
moved_out=0 (which would falsely claim "nobody left"), this code treats an
all-null column as "not available" and says so, and same for net_migration
whenever either side is missing. If you find a query shape that reliably
populates MOVEDOUT (e.g. a newer ACS vintage, or explicit county-pair
queries), simplify this back down -- see the "Next steps" note in the README.

Both lookups are wrapped in try/except and cached in memory, and return None
on any failure -- a broken or slow Census API degrades to "not available"
rather than a 500 error for the rest of the app.
"""
import httpx

from app.config import settings

GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
FLOWS_URL_TEMPLATE = "https://api.census.gov/data/{year}/acs/flows"
FLOWS_YEAR = 2021  # most recent year published as of when this was written -- bump if a newer one exists

_county_cache: dict[tuple[float, float], dict | None] = {}
_flows_cache: dict[tuple[str, str], dict | None] = {}


def get_county_for_point(lat: float, lng: float) -> dict | None:
    """Returns {"state_fips", "county_fips", "county_name"} or None."""
    key = (round(lat, 3), round(lng, 3))
    if key in _county_cache:
        return _county_cache[key]

    try:
        resp = httpx.get(
            GEOCODER_URL,
            params={
                "x": lng,
                "y": lat,
                "benchmark": "Public_AR_Current",
                "vintage": "Current_Current",
                "format": "json",
            },
            timeout=6.0,
        )
        resp.raise_for_status()
        counties = resp.json()["result"]["geographies"].get("Counties", [])
        if not counties:
            result = None
        else:
            c = counties[0]
            result = {"state_fips": c["STATE"], "county_fips": c["COUNTY"], "county_name": c["NAME"]}
    except Exception:
        result = None

    _county_cache[key] = result
    return result


def get_migration_for_county(state_fips: str, county_fips: str) -> dict | None:
    if not settings.census_api_key:
        return None

    key = (state_fips, county_fips)
    if key in _flows_cache:
        return _flows_cache[key]

    try:
        resp = httpx.get(
            FLOWS_URL_TEMPLATE.format(year=FLOWS_YEAR),
            params={
                "get": "FULL1_NAME,MOVEDIN,MOVEDOUT,MOVEDNET",
                "for": f"county:{county_fips}",
                "in": f"state:{state_fips}",
                "key": settings.census_api_key,
            },
            timeout=8.0,
        )
        resp.raise_for_status()
        rows = resp.json()
        if len(rows) < 2:
            result = None
        else:
            header, *data_rows = rows
            idx = {name: i for i, name in enumerate(header)}

            def safe_int_or_none(v):
                if v is None:
                    return None
                try:
                    return max(int(v), 0)
                except (TypeError, ValueError):
                    return None

            def summed_or_none(col):
                # None only when EVERY row is null/unparseable for this column --
                # that means Census didn't publish this figure at all (see the
                # module docstring), as opposed to individual suppressed rows,
                # which just don't contribute to the sum.
                vals = [safe_int_or_none(r[idx[col]]) for r in data_rows]
                if not any(v is not None for v in vals):
                    return None
                return sum(v for v in vals if v is not None)

            moved_in = summed_or_none("MOVEDIN")
            moved_out = summed_or_none("MOVEDOUT")
            net_migration = (moved_in - moved_out) if (moved_in is not None and moved_out is not None) else None
            result = {
                "year": FLOWS_YEAR,
                "moved_in": moved_in,
                "moved_out": moved_out,
                "net_migration": net_migration,
                "moved_out_available": moved_out is not None,
            }
    except Exception:
        result = None

    _flows_cache[key] = result
    return result


def get_migration_for_point(lat: float, lng: float) -> dict | None:
    county = get_county_for_point(lat, lng)
    if not county:
        return None
    migration = get_migration_for_county(county["state_fips"], county["county_fips"])
    if not migration:
        return None
    return {**county, **migration}
