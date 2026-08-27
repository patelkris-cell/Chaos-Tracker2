from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import analytics, places, schemas
from app.deps import get_db

router = APIRouter(prefix="/areas", tags=["areas"])


@router.get("/search", response_model=schemas.PlaceSearchResponse)
def search(
    q: str = Query(..., min_length=1, max_length=200),
    lat: Optional[float] = Query(None, description="Current map center, to bias results toward that area"),
    lng: Optional[float] = Query(None),
):
    """Backs the map's search box -- addresses, cities, ZIPs, landmarks, and
    business names, via Nominatim (see app/places.py). Replaced the old
    single-result /areas/geocode (Census-only, addresses only) so the
    frontend can offer several candidates instead of silently committing to
    the first match."""
    near = (lat, lng) if lat is not None and lng is not None else None
    results = places.search_places(q, near=near)
    return schemas.PlaceSearchResponse(results=results)


@router.get("/insights", response_model=schemas.AreaInsights)
def area_insights(
    lat: float = Query(...),
    lng: float = Query(...),
    radius_km: float = Query(2.0, gt=0, le=25),
    db: Session = Depends(get_db),
):
    """
    This is the endpoint behind the frontend's "Check area" / area-verification
    flow, and the same logic the chatbot's get_area_trend tool calls -- given a
    point (typed address or GPS), report whether reported chaos nearby has
    trended up or down over the last 6 months.

    Population/median income/area size are NOT included here yet -- those need
    the Census ACS integration (see README "Next: demographics"). Everything
    else is computed live from real Incident rows.
    """
    result = analytics.compute_area_insights(db, lat, lng, radius_km)
    return schemas.AreaInsights(**result)
