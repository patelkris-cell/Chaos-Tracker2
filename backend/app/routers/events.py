import datetime
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import discovery, models, schemas
from app.config import settings
from app.deps import get_current_user, get_db

router = APIRouter(prefix="/events", tags=["events"])


def _serialize_event(event: models.Event) -> schemas.EventOut:
    ups = sum(1 for r in event.reactions if r.is_up)
    downs = sum(1 for r in event.reactions if not r.is_up)
    return schemas.EventOut(
        id=event.id,
        name=event.name,
        icon=event.icon,
        description=event.description,
        impact=event.impact,
        lat=event.lat,
        lng=event.lng,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        venue_name=event.venue_name,
        expected_attendance=event.expected_attendance,
        chaos_score=event.chaos_score,
        source_url=event.source_url,
        ai_generated=event.ai_generated,
        thumbs_up=ups,
        thumbs_down=downs,
        comment_count=len(event.event_comments),
    )


def _serialize_event_comment(comment: models.EventComment) -> schemas.EventCommentOut:
    return schemas.EventCommentOut(
        id=comment.id,
        event_id=comment.event_id,
        author_id=comment.author_id,
        author_username=comment.author.username,
        text=comment.text,
        image_url=comment.image_url,
        gif_url=comment.gif_url,
        created_at=comment.created_at,
        edited_at=comment.edited_at,
    )


def _get_event_or_404(event_id: int, db: Session) -> models.Event:
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    return event


@router.post("", response_model=schemas.EventOut, status_code=201)
def create_event(
    body: schemas.EventCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    event = models.Event(**body.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return _serialize_event(event)


@router.get("", response_model=list[schemas.EventOut])
def list_events(db: Session = Depends(get_db)):
    events = db.query(models.Event).order_by(models.Event.starts_at.asc()).all()
    return [_serialize_event(e) for e in events]


@router.post("/discover", response_model=schemas.EventDiscoverResult)
def discover_events(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Has Claude web-search for real upcoming events near the configured
    area (see app/config.py's discovery_counties) and adds any new ones.
    Requires login since each call costs real money (Claude web search) --
    see app/discovery.py. Takes 10-30+ seconds; the frontend should show a
    loading state rather than assume this is instant."""
    if not settings.anthropic_api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY is not set -- event discovery is disabled until it is.")

    try:
        found = discovery.discover_events()
    except Exception as e:
        raise HTTPException(502, f"Event discovery failed: {e}")

    added = []
    skipped = 0
    # Dedup against existing AI-discovered events by (name, starts_at date) --
    # cheap and good enough to stop repeated clicks from spamming duplicates,
    # without needing exact source_url equality (the same event sometimes
    # gets a slightly different URL across searches).
    existing = {
        (e.name.strip().lower(), e.starts_at.date())
        for e in db.query(models.Event).filter(models.Event.ai_generated.is_(True)).all()
    }
    for item in found:
        key = (item["name"].strip().lower(), item["starts_at"].date())
        if key in existing:
            skipped += 1
            continue
        event = models.Event(**item)
        db.add(event)
        added.append(event)
        existing.add(key)

    db.commit()
    for event in added:
        db.refresh(event)

    return schemas.EventDiscoverResult(
        added=len(added),
        skipped_existing=skipped,
        events=[_serialize_event(e) for e in added],
    )


@router.get("/{event_id}", response_model=schemas.EventOut)
def get_event(event_id: int, db: Session = Depends(get_db)):
    return _serialize_event(_get_event_or_404(event_id, db))


@router.post("/{event_id}/reactions", response_model=schemas.EventReactionResult)
def react_to_event(
    event_id: int,
    body: schemas.EventReactionIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    event = _get_event_or_404(event_id, db)
    existing = (
        db.query(models.EventReaction)
        .filter(models.EventReaction.event_id == event_id, models.EventReaction.user_id == current_user.id)
        .first()
    )
    my_reaction = body.is_up
    if existing and existing.is_up == body.is_up:
        # Clicking the same thumb again retracts the vote.
        db.delete(existing)
        my_reaction = None
    elif existing:
        # Switching from up to down (or vice versa).
        existing.is_up = body.is_up
    else:
        db.add(models.EventReaction(event_id=event_id, user_id=current_user.id, is_up=body.is_up))
    db.commit()
    db.refresh(event)

    ups = sum(1 for r in event.reactions if r.is_up)
    downs = sum(1 for r in event.reactions if not r.is_up)
    return schemas.EventReactionResult(event_id=event_id, thumbs_up=ups, thumbs_down=downs, my_reaction=my_reaction)


@router.get("/{event_id}/comments", response_model=list[schemas.EventCommentOut])
def list_event_comments(event_id: int, db: Session = Depends(get_db)):
    _get_event_or_404(event_id, db)
    comments = (
        db.query(models.EventComment)
        .filter(models.EventComment.event_id == event_id)
        .order_by(models.EventComment.created_at.asc())
        .all()
    )
    return [_serialize_event_comment(c) for c in comments]


@router.post("/{event_id}/comments", response_model=schemas.EventCommentOut, status_code=201)
def add_event_comment(
    event_id: int,
    body: schemas.EventCommentCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_event_or_404(event_id, db)
    comment = models.EventComment(
        event_id=event_id,
        author_id=current_user.id,
        text=body.text,
        image_url=body.image_url,
        gif_url=body.gif_url,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return _serialize_event_comment(comment)


def _get_owned_event_comment(comment_id: int, current_user: models.User, db: Session) -> models.EventComment:
    comment = db.query(models.EventComment).filter(models.EventComment.id == comment_id).first()
    if not comment:
        raise HTTPException(404, "Comment not found")
    if comment.author_id != current_user.id:
        raise HTTPException(403, "You can only edit or delete your own comments")
    return comment


@router.patch("/comments/{comment_id}", response_model=schemas.EventCommentOut)
def edit_event_comment(
    comment_id: int,
    body: schemas.EventCommentUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    comment = _get_owned_event_comment(comment_id, current_user, db)
    comment.text = body.text
    comment.edited_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(comment)
    return _serialize_event_comment(comment)


@router.delete("/comments/{comment_id}", status_code=204)
def delete_event_comment(
    comment_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    comment = _get_owned_event_comment(comment_id, current_user, db)
    db.delete(comment)
    db.commit()
