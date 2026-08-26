from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas
from app.deps import get_current_user, get_db

router = APIRouter(prefix="/users", tags=["users"])


@router.patch("/me/home-location", response_model=schemas.UserOut)
def update_home_location(
    body: schemas.HomeLocationUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.home_location = body.home_location
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/me/stats", response_model=schemas.UserProfileStats)
def my_stats(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    reports_submitted = (
        db.query(func.count(models.Incident.id))
        .filter(models.Incident.reporter_id == current_user.id)
        .scalar()
    ) or 0

    verified_reports = (
        db.query(func.count(models.Incident.id))
        .filter(models.Incident.reporter_id == current_user.id, models.Incident.verified.is_(True))
        .scalar()
    ) or 0

    corroborations_given = (
        db.query(func.count(models.VerificationVote.id))
        .filter(models.VerificationVote.user_id == current_user.id)
        .scalar()
    ) or 0

    accuracy = (verified_reports / reports_submitted * 100) if reports_submitted else 0.0

    return schemas.UserProfileStats(
        reports_submitted=reports_submitted,
        verified_accuracy_pct=round(accuracy, 1),
        corroborations_given=corroborations_given,
        trust_score=current_user.trust_score,
    )
