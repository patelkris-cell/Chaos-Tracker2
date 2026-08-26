from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import settings
from app.deps import get_current_user, get_db

router = APIRouter(prefix="/incidents", tags=["verify"])


@router.post("/{incident_id}/vote", response_model=schemas.VoteResult)
def vote(
    incident_id: int,
    body: schemas.VoteRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    incident = db.query(models.Incident).filter(models.Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(404, "Incident not found")
    if incident.reporter_id == current_user.id:
        raise HTTPException(400, "You can't vote on your own report")

    existing = (
        db.query(models.VerificationVote)
        .filter(
            models.VerificationVote.incident_id == incident_id,
            models.VerificationVote.user_id == current_user.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(400, "You've already voted on this report")

    db.add(models.VerificationVote(incident_id=incident_id, user_id=current_user.id, confirm=body.confirm))

    if body.confirm:
        incident.confirms += 1
    else:
        incident.denies += 1

    if incident.confirms >= settings.verification_threshold:
        incident.verified = True
        # small trust bump for the original reporter once corroborated
        if incident.reporter_id:
            reporter = db.query(models.User).filter(models.User.id == incident.reporter_id).first()
            if reporter:
                reporter.trust_score = min(100, reporter.trust_score + 2)

    db.commit()
    db.refresh(incident)

    return schemas.VoteResult(
        incident_id=incident.id, confirms=incident.confirms, denies=incident.denies, verified=incident.verified
    )
