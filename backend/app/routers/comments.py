import datetime
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.deps import get_current_user, get_db

router = APIRouter(tags=["comments"])


def _serialize(comment: models.Comment) -> schemas.CommentOut:
    counts = Counter(r.emoji for r in comment.reactions)
    return schemas.CommentOut(
        id=comment.id,
        incident_id=comment.incident_id,
        author_id=comment.author_id,
        author_username=comment.author.username,
        text=comment.text,
        image_url=comment.image_url,
        gif_url=comment.gif_url,
        created_at=comment.created_at,
        edited_at=comment.edited_at,
        reactions=dict(counts),
    )


@router.post("/incidents/{incident_id}/comments", response_model=schemas.CommentOut, status_code=201)
def add_comment(
    incident_id: int,
    body: schemas.CommentCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not db.query(models.Incident).filter(models.Incident.id == incident_id).first():
        raise HTTPException(404, "Incident not found")

    comment = models.Comment(
        incident_id=incident_id,
        author_id=current_user.id,
        text=body.text,
        image_url=body.image_url,
        gif_url=body.gif_url,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return _serialize(comment)


@router.get("/incidents/{incident_id}/comments", response_model=list[schemas.CommentOut])
def list_comments(incident_id: int, db: Session = Depends(get_db)):
    comments = (
        db.query(models.Comment)
        .filter(models.Comment.incident_id == incident_id)
        .order_by(models.Comment.created_at.asc())
        .all()
    )
    return [_serialize(c) for c in comments]


def _get_owned_comment(comment_id: int, current_user: models.User, db: Session) -> models.Comment:
    comment = db.query(models.Comment).filter(models.Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(404, "Comment not found")
    if comment.author_id != current_user.id:
        raise HTTPException(403, "You can only edit or delete your own comments")
    return comment


@router.patch("/comments/{comment_id}", response_model=schemas.CommentOut)
def edit_comment(
    comment_id: int,
    body: schemas.CommentUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    comment = _get_owned_comment(comment_id, current_user, db)
    comment.text = body.text
    comment.edited_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(comment)
    return _serialize(comment)


@router.delete("/comments/{comment_id}", status_code=204)
def delete_comment(
    comment_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    comment = _get_owned_comment(comment_id, current_user, db)
    db.delete(comment)
    db.commit()


@router.post("/comments/{comment_id}/reactions", response_model=schemas.CommentOut)
def toggle_reaction(
    comment_id: int,
    body: schemas.ReactionIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    comment = db.query(models.Comment).filter(models.Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(404, "Comment not found")

    existing = (
        db.query(models.Reaction)
        .filter(
            models.Reaction.comment_id == comment_id,
            models.Reaction.user_id == current_user.id,
            models.Reaction.emoji == body.emoji,
        )
        .first()
    )
    if existing:
        db.delete(existing)  # toggle off
    else:
        db.add(models.Reaction(comment_id=comment_id, user_id=current_user.id, emoji=body.emoji))
    db.commit()
    db.refresh(comment)
    return _serialize(comment)
