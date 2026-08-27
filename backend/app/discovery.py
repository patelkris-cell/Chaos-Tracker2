"""
AI-powered discovery of REAL upcoming events and REAL local news, via Claude's
web search tool. Both functions follow the same shape: give Claude web search
plus one custom "record_*" tool, instruct it to only report what it actually
found (never invent anything), then independently geocode each result
ourselves via Nominatim (app/places.py) rather than trusting any coordinates
Claude might guess -- an item that doesn't geocode to a real place is
dropped rather than plotted somewhere wrong.

This only runs on-demand (a user clicking "discover" in the frontend), not on
a schedule -- Render's free web services can't run background jobs, and this
is a single-user hobby app, not something that needs to stay fresh by itself.

Costs real money per call (Claude web search is $10/1000 searches, capped at
MAX_SEARCHES_PER_CALL below, plus normal token costs) -- that's why both
routers require login (see app/routers/events.py and app/routers/news.py).
"""
import datetime
import json
import time

from anthropic import Anthropic

from app import places
from app.config import settings

MAX_SEARCHES_PER_CALL = 6
MODEL_MAX_TOKENS = 4096

# Nominatim's usage policy caps free public-instance traffic at ~1
# request/second and rate-limits (HTTP 429) any client that goes over it --
# see app/places.py. discover_events()/discover_news() each geocode several
# items back-to-back; without a delay between them, a single "discover"
# click can burst 8-16 geocode calls in a couple seconds and trip that
# limit. Once tripped, EVERY geocode call fails (not just the AI-discovery
# ones) until it clears, which silently breaks normal map search and Add
# Chaos pin placement too -- this happened for real (see git history).
GEOCODE_THROTTLE_SECONDS = 1.1


def _client() -> Anthropic:
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set -- discovery is disabled until it is.")
    return Anthropic(api_key=settings.anthropic_api_key)


def _region_phrase() -> str:
    counties = ", ".join(settings.discovery_county_list)
    return f"{counties} counties, {settings.discovery_state}"


def _geocode_first(address_or_place: str) -> tuple[float, float] | None:
    """Geocodes via the same Nominatim search the map's own address search
    uses. Deliberately does NOT append the full multi-county discovery
    region as a hint -- Nominatim's free-text matching gets confused by a
    long list of counties tacked onto an otherwise-good address and returns
    nothing (confirmed live: an address that geocodes fine on its own
    returns zero results once "Middlesex, Union, Somerset..." is appended).
    Claude is asked for a specific real address/place, which is normally
    enough on its own; only add the state if it's missing entirely."""
    query = address_or_place.strip()
    state = settings.discovery_state
    if state and state.lower() not in query.lower():
        query = f"{query}, {state}"
    time.sleep(GEOCODE_THROTTLE_SECONDS)  # stay under Nominatim's ~1 req/sec policy -- see module-level comment
    results = places.search_places(query, limit=1)
    if not results:
        return None
    return results[0]["lat"], results[0]["lng"]


def _parse_dt(value) -> datetime.datetime | None:
    if not value:
        return None
    try:
        # Claude is asked for ISO 8601; be lenient about a trailing "Z".
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


RECORD_EVENTS_TOOL = {
    "name": "record_events",
    "description": "Record the real upcoming events you found via web search, as structured data.",
    "input_schema": {
        "type": "object",
        "properties": {
            "events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "venue_name": {"type": "string"},
                        "address_or_place": {
                            "type": "string",
                            "description": "the real venue address or place name, for geocoding -- be as specific as possible",
                        },
                        "description": {"type": "string", "description": "1-3 sentences, factual"},
                        "icon": {"type": "string", "description": "a single emoji representing the event type"},
                        "starts_at": {"type": "string", "description": "ISO 8601 datetime; if only a date is known, use 19:00 local time"},
                        "ends_at": {"type": ["string", "null"]},
                        "expected_attendance": {"type": ["integer", "null"], "description": "best real estimate, or null if unknown"},
                        "chaos_score": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 100,
                            "description": "0=calm/small gathering, 100=massive/highly disruptive -- based on expected crowd size, traffic, and noise",
                        },
                        "impact": {"type": "string", "enum": ["moderate", "high", "elevated"]},
                        "source_url": {"type": "string", "description": "the real URL you found this from"},
                    },
                    "required": ["name", "address_or_place", "description", "starts_at", "chaos_score", "impact", "source_url"],
                },
            }
        },
        "required": ["events"],
    },
}

RECORD_NEWS_TOOL = {
    "name": "record_news",
    "description": "Record the real local news items you found via web search, as structured data.",
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "headline": {"type": "string"},
                        "summary": {"type": "string", "description": "1-3 sentences, factual, no embellishment"},
                        "category": {"type": "string", "enum": ["accident", "shooting", "protest", "fire", "weather", "other"]},
                        "address_or_place": {
                            "type": "string",
                            "description": "the most specific real place named in the article, for geocoding",
                        },
                        "published_at": {"type": "string", "description": "ISO 8601 date"},
                        "source_name": {"type": "string", "description": "the real publication/outlet name"},
                        "source_url": {"type": "string", "description": "the real article URL"},
                    },
                    "required": ["headline", "summary", "category", "address_or_place", "published_at", "source_name", "source_url"],
                },
            }
        },
        "required": ["items"],
    },
}


def _run_with_tool(system: str, user_message: str, tool: dict) -> list[dict]:
    """Shared plumbing: call Claude with web_search + the given custom tool,
    return whatever list the custom tool call contains (the key name inside
    `input` differs between record_events/record_news, so this returns the
    whole `input` dict and callers pull out the field they expect)."""
    client = _client()
    messages = [{"role": "user", "content": user_message}]

    for _ in range(2):  # one retry if it forgets to call the tool the first time
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=MODEL_MAX_TOKENS,
            system=system,
            tools=[
                {"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_SEARCHES_PER_CALL},
                tool,
            ],
            messages=messages,
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == tool["name"]:
                return block.input

        # Didn't call it -- nudge once, with everything so far as context.
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": f"Now call {tool['name']} with what you found (an empty list if truly nothing)."})

    return {}


def discover_events() -> list[dict]:
    """Returns a list of dicts shaped like schemas.EventCreate plus the extra
    AI-discovery fields, with real geocoded lat/lng -- ready to insert as
    models.Event rows. Items that don't geocode, or whose end (or start, if
    no end) time is already in the past, are dropped."""
    system = (
        "You find REAL upcoming public events (concerts, festivals, sports games, "
        "parades, fairs, large community gatherings) in a specified region over the "
        "next 30 days, using web search. Only include events you actually found via "
        "search with a real, specific source URL -- never invent an event or guess "
        "at one that 'probably' happens annually without confirming this year's date. "
        "For each, estimate a 0-100 chaos_score reflecting expected crowd size, "
        "traffic disruption, and noise. When you have gathered up to 8 real events, "
        "call record_events with the structured list. If you find zero, call "
        "record_events with an empty list -- do not pad it with guesses."
    )
    user_message = f"Find real upcoming public events in {_region_phrase()} over the next 30 days."
    result = _run_with_tool(system, user_message, RECORD_EVENTS_TOOL)

    now = datetime.datetime.utcnow()
    out = []
    for item in result.get("events", []):
        starts_at = _parse_dt(item.get("starts_at"))
        ends_at = _parse_dt(item.get("ends_at"))
        if not starts_at:
            continue
        if (ends_at or starts_at) < now:
            continue  # stale search result already in the past -- drop rather than show a finished event as "upcoming"

        geocoded = _geocode_first(item.get("address_or_place", ""))
        if not geocoded:
            continue  # couldn't confirm a real place -- drop rather than guess coordinates
        lat, lng = geocoded

        out.append({
            "name": (item.get("name") or "Untitled event")[:120],
            "icon": item.get("icon") or "📅",
            "description": item.get("description") or "",
            "impact": item.get("impact") if item.get("impact") in ("moderate", "high", "elevated") else "moderate",
            "lat": lat,
            "lng": lng,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "venue_name": item.get("venue_name"),
            "expected_attendance": item.get("expected_attendance"),
            "chaos_score": max(0, min(100, int(item["chaos_score"]))) if item.get("chaos_score") is not None else None,
            "source_url": item.get("source_url"),
            "ai_generated": True,
        })
    return out


def discover_news() -> list[dict]:
    """Returns a list of dicts shaped like models.NewsReport, with real
    geocoded lat/lng. Items that don't geocode are dropped."""
    system = (
        "You find REAL, recent local news reports (last 14 days) about accidents, "
        "fires, crime, protests, or severe weather impacts in a specified region, "
        "using web search. This feeds a public safety map, so accuracy matters: only "
        "include items from an actual news article you found via search, with its "
        "real headline, source name, and source URL -- never invent or embellish an "
        "incident, and never include something you're not confident is real and recent. "
        "When done (up to 8 items), call record_news. If you find nothing real and "
        "recent, call record_news with an empty list rather than including anything "
        "uncertain."
    )
    user_message = (
        f"Find real recent local news about accidents, fires, crime, protests, or "
        f"severe weather in {_region_phrase()}."
    )
    result = _run_with_tool(system, user_message, RECORD_NEWS_TOOL)

    out = []
    for item in result.get("items", []):
        if not item.get("source_url") or not item.get("headline"):
            continue
        geocoded = _geocode_first(item.get("address_or_place", ""))
        if not geocoded:
            continue
        lat, lng = geocoded

        out.append({
            "headline": item["headline"][:300],
            "summary": item.get("summary") or "",
            "category": item.get("category") if item.get("category") in
                        ("accident", "shooting", "protest", "fire", "weather", "other") else "other",
            "lat": lat,
            "lng": lng,
            "source_name": item.get("source_name") or "Unknown source",
            "source_url": item["source_url"],
            "published_at": _parse_dt(item.get("published_at")),
        })
    return out
