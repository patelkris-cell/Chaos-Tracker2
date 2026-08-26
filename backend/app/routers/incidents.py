from collections import Counter
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import geo, models, schemas
from app.deps import get_current_user, get_db

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.post("", response_model=schemas.IncidentOut, status_code=201)
def create_incident(
    body: schemas.IncidentCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    incident = models.Incident(
        reporter_id=current_user.id,
        category=body.category,
        severity=body.severity,
        description=body.description,
        lat=body.lat,
        lng=body.lng,
        image_url=body.image_url,
        gif_url=body.gif_url,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


@router.get("", response_model=list[schemas.IncidentOut])
def list_incidents(
    category: Optional[str] = None,
    verified: Optional[bool] = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(models.Incident)
    if category and category != "all":
        q = q.filter(models.Incident.category == category)
    if verified is not None:
        q = q.filter(models.Incident.verified == verified)
    return q.order_by(models.Incident.created_at.desc()).limit(limit).all()


@router.get("/pending", response_model=list[schemas.IncidentOut])
def pending_incidents(db: Session = Depends(get_db)):
    return (
        db.query(models.Incident)
        .filter(models.Incident.verified.is_(False))
        .order_by(models.Incident.created_at.desc())
        .all()
    )


@router.get("/heatmap", response_model=list[schemas.HexCell])
def heatmap(
    resolution: int = Query(8, ge=4, le=10, description="H3 resolution -- 8 is roughly neighborhood-sized cells"),
    category: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.Incident.lat, models.Incident.lng)
    if category and category != "all":
        q = q.filter(models.Incident.category == category)
    points = q.all()

    if not points:
        return []

    counts: Counter[str] = Counter()
    for lat, lng in points:
        counts[geo.cell_for_point(lat, lng, resolution)] += 1

    max_count = max(counts.values())
    cells = []
    for h3_index, count in counts.items():
        center_lat, center_lng = geo.cell_center(h3_index)
        cells.append(
            schemas.HexCell(
                h3_index=h3_index,
                lat=center_lat,
                lng=center_lng,
                boundary=geo.cell_boundary(h3_index),
                count=count,
                density=round(count / max_count, 3),
            )
        )
    return cells


@router.get("/{incident_id}", response_model=schemas.IncidentOut)
def get_incident(incident_id: int, db: Session = Depends(get_db)):
    incident = db.query(models.Incident).filter(models.Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(404, "Incident not found")
    return incident
