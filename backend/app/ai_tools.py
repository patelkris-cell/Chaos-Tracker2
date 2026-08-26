"""
Tool definitions handed to Claude for the /chat endpoint, plus the dispatcher
that actually runs one when Claude asks for it. Every tool hits either our
own database (real, tested) or the Census APIs (real API, live-tested
2026-08-25 -- see app/census.py) -- Claude never answers a data question
from its own guess.
"""
from sqlalchemy.orm import Session

from app import analytics, census

TOOLS = [
    {
        "name": "get_area_trend",
        "description": (
            "Get the count of reported incidents near a location and whether they've "
            "trended up or down over the last 6 months, plus a 30-day count and the "
            "verified rate. Use this for any question about rising/falling crime, "
            "safety, or 'chaos' in an area."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Latitude of the area"},
                "lng": {"type": "number", "description": "Longitude of the area"},
                "radius_km": {"type": "number", "description": "Search radius in km, default 2", "default": 2.0},
            },
            "required": ["lat", "lng"],
        },
    },
    {
        "name": "get_incident_breakdown",
        "description": (
            "Get a count of nearby incidents broken down by category (accident, "
            "shooting, protest, fire, weather, other). Use this for 'what kind of "
            "incidents happen here' type questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lng": {"type": "number"},
                "radius_km": {"type": "number", "default": 2.0},
            },
            "required": ["lat", "lng"],
        },
    },
    {
        "name": "get_county_migration",
        "description": (
            "Get how many people moved into (and, when published, out of) the COUNTY "
            "containing a location, from Census Bureau data (most recent published "
            "year). This is county-level, not neighborhood-level -- always say so if "
            "the user asked about a specific neighborhood or block. May be unavailable "
            "if no Census API key is configured or the lookup fails. Census frequently "
            "only publishes the inbound number for a given county -- check the "
            "'moved_out_available' field, and if it's false, only report moved_in and "
            "explicitly say outbound/net figures aren't published for this area rather "
            "than implying nobody left."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"lat": {"type": "number"}, "lng": {"type": "number"}},
            "required": ["lat", "lng"],
        },
    },
]


def run_tool(name: str, tool_input: dict, db: Session) -> dict:
    if name == "get_area_trend":
        return analytics.compute_area_insights(
            db, tool_input["lat"], tool_input["lng"], tool_input.get("radius_km", 2.0)
        )

    if name == "get_incident_breakdown":
        return analytics.compute_incident_breakdown(
            db, tool_input["lat"], tool_input["lng"], tool_input.get("radius_km", 2.0)
        )

    if name == "get_county_migration":
        result = census.get_migration_for_point(tool_input["lat"], tool_input["lng"])
        if result is None:
            return {
                "available": False,
                "reason": "Census lookup failed, the point is outside the US, or CENSUS_API_KEY isn't set.",
            }
        return {"available": True, **result}

    return {"error": f"Unknown tool '{name}'"}
