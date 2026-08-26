"""
Shared query logic used by both the /areas/insights REST endpoint and the
chatbot's tools -- kept in one place so the chatbot can never report a
different trend number than the map does.
"""
import datetime
from collections import Counter

from sqlalchemy.orm import Session

from app import geo, models


def compute_area_insights(db: Session, lat: float, lng: float, radius_km: float = 2.0) -> dict:
    now = datetime.datetime.utcnow()
    six_mo_ago = now - datetime.timedelta(days=182)
    twelve_mo_ago = now - datetime.timedelta(days=365)
    thirty_days_ago = now - datetime.timedelta(days=30)

    min_lat, max_lat, min_lng, max_lng = geo.bounding_box(lat, lng, radius_km)
    candidates = (
        db.query(models.Incident)
        .filter(
            models.Incident.lat.between(min_lat, max_lat),
            models.Incident.lng.between(min_lng, max_lng),
            models.Incident.created_at >= twelve_mo_ago,
        )
        .all()
    )
    nearby = [i for i in candidates if geo.haversine_km(lat, lng, i.lat, i.lng) <= radius_km]

    recent_6mo = [i for i in nearby if i.created_at >= six_mo_ago]
    prior_6mo = [i for i in nearby if i.created_at < six_mo_ago]

    if prior_6mo:
        trend_pct = round((len(recent_6mo) - len(prior_6mo)) / len(prior_6mo) * 100, 1)
    elif recent_6mo:
        trend_pct = 100.0
    else:
        trend_pct = 0.0

    reports_30d = len([i for i in nearby if i.created_at >= thirty_days_ago])
    verified_count = len([i for i in nearby if i.verified])
    verified_rate = round(verified_count / len(nearby) * 100, 1) if nearby else 0.0

    return {
        "lat": lat,
        "lng": lng,
        "radius_km": radius_km,
        "reports_last_6mo": len(recent_6mo),
        "reports_prior_6mo": len(prior_6mo),
        "trend_pct": trend_pct,
        "reports_30d": reports_30d,
        "verified_rate_pct": verified_rate,
    }


def compute_incident_breakdown(db: Session, lat: float, lng: float, radius_km: float = 2.0) -> dict:
    min_lat, max_lat, min_lng, max_lng = geo.bounding_box(lat, lng, radius_km)
    candidates = (
        db.query(models.Incident)
        .filter(models.Incident.lat.between(min_lat, max_lat), models.Incident.lng.between(min_lng, max_lng))
        .all()
    )
    nearby = [i for i in candidates if geo.haversine_km(lat, lng, i.lat, i.lng) <= radius_km]
    counts = Counter(i.category for i in nearby)
    return {
        "lat": lat,
        "lng": lng,
        "radius_km": radius_km,
        "total_incidents": len(nearby),
        "by_category": dict(counts),
    }
