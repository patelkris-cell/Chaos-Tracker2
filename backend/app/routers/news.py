"""
Real local news, discovered via AI web search (app/discovery.py). Kept
completely separate from /incidents -- these are secondhand news summaries,
not firsthand user reports, and the frontend renders them as a visually
distinct map layer so nothing looks more verified than it actually is.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import discovery, models, schemas
from app.config import settings
from app.deps import get_current_user, get_db

router = APIRouter(prefix="/news", tags=["news"])


def _serialize(item: models.NewsReport) -> schemas.NewsReportOut:
    return schemas.NewsReportOut(
        id=item.id,
        headline=item.headline,
        summary=item.summary,
        category=item.category,
        lat=item.lat,
        lng=item.lng,
        source_name=item.source_name,
        source_url=item.source_url,
        published_at=item.published_at,
        created_at=item.created_at,
    )


@router.get("", response_model=list[schemas.NewsReportOut])
def list_news(db: Session = Depends(get_db)):
    items = db.query(models.NewsReport).order_by(models.NewsReport.created_at.desc()).limit(100).all()
    return [_serialize(i) for i in items]


@router.post("/discover", response_model=schemas.NewsDiscoverResult)
def discover_news(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Has Claude web-search for real recent local news near the configured
    area (see app/config.py's discovery_counties) and adds any new items.
    Requires login since each call costs real money (Claude web search) --
    see app/discovery.py. Takes 10-30+ seconds; the frontend should show a
    loading state rather than assume this is instant."""
    if not settings.anthropic_api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY is not set -- news discovery is disabled until it is.")

    try:
        found = discovery.discover_news()
    except Exception as e:
        raise HTTPException(502, f"News discovery failed: {e}")

    added = []
    skipped = 0
    existing_urls = {u for (u,) in db.query(models.NewsReport.source_url).all()}
    for item in found:
        if item["source_url"] in existing_urls:
            skipped += 1
            continue
        report = models.NewsReport(**item)
        db.add(report)
        added.append(report)
        existing_urls.add(item["source_url"])

    db.commit()
    for report in added:
        db.refresh(report)

    return schemas.NewsDiscoverResult(
        added=len(added),
        skipped_existing=skipped,
        items=[_serialize(i) for i in added],
    )
