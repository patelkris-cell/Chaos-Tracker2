import datetime
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import emailer, models, otp, schemas, security
from app.config import settings
from app.deps import get_current_user, get_db

router = APIRouter(prefix="/auth", tags=["auth"])

RESET_LINK_TTL_MINUTES = 30
RESET_SMS_CODE_TTL_MINUTES = 15


@router.post("/register", response_model=schemas.TokenResponse, status_code=201)
def register(body: schemas.RegisterRequest, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == body.email).first():
        raise HTTPException(400, "An account with that email already exists")
    if db.query(models.User).filter(models.User.username == body.username).first():
        raise HTTPException(400, "That username is taken")

    user = models.User(
        username=body.username,
        email=body.email,
        password_hash=security.hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = security.create_access_token(user.id)
    return schemas.TokenResponse(access_token=token, user=user)


@router.post("/login", response_model=schemas.TokenResponse)
def login(body: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == body.email).first()
    if not user or not security.verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")

    token = security.create_access_token(user.id)
    return schemas.TokenResponse(access_token=token, user=user)


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user


def _phone_taken_by_someone_else(phone_number: str, current_user: models.User, db: Session) -> bool:
    """One verified account per phone number -- checked at both request and
    confirm time (confirm is the one that actually matters for a race
    between two people verifying the same real number at once; request is
    just a fail-fast so nobody wastes an SMS credit on a doomed attempt)."""
    return (
        db.query(models.User)
        .filter(
            models.User.phone_number == phone_number,
            models.User.phone_verified.is_(True),
            models.User.id != current_user.id,
        )
        .first()
        is not None
    )


@router.post("/phone/request")
def request_phone_verification(
    body: schemas.PhoneRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if _phone_taken_by_someone_else(body.phone_number, current_user, db):
        raise HTTPException(400, "That phone number is already verified on another account.")
    try:
        code, expires_at = otp.send_otp(body.phone_number)
    except Exception as e:
        # Covers real Twilio failures (bad phone format, unverified trial
        # number, Twilio outage, etc.) as well as our own missing-config
        # RuntimeError -- either way, tell the caller plainly instead of a
        # bare 500.
        raise HTTPException(400, f"Couldn't send verification code: {e}")

    current_user.phone_number = body.phone_number
    # In twilio mode `code` is always None -- there is nothing of ours to
    # store, Twilio is the source of truth (see app/otp.py).
    current_user.pending_otp_code = code
    current_user.pending_otp_expires = expires_at
    db.commit()

    response = {"message": "Verification code sent."}
    if settings.otp_provider == "mock":
        # Only ever echoed back in mock mode -- a real SMS provider would not do this.
        response["mock_code"] = code
    return response


@router.post("/phone/confirm", response_model=schemas.UserOut)
def confirm_phone_verification(
    body: schemas.PhoneConfirm,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.pending_otp_expires or not current_user.phone_number:
        raise HTTPException(400, "No verification code was requested")
    if datetime.datetime.utcnow() > current_user.pending_otp_expires:
        raise HTTPException(400, "That code has expired -- request a new one")

    try:
        correct = otp.check_otp(current_user.phone_number, body.code, current_user.pending_otp_code)
    except Exception as e:
        raise HTTPException(400, f"Couldn't verify code: {e}")

    if not correct:
        raise HTTPException(400, "Incorrect code")

    # Re-check right before committing -- guards the race where two people
    # request/confirm the same real number at nearly the same time.
    if _phone_taken_by_someone_else(current_user.phone_number, current_user, db):
        raise HTTPException(400, "That phone number was just verified on another account.")

    current_user.phone_verified = True
    current_user.pending_otp_code = None
    current_user.pending_otp_expires = None
    db.commit()
    db.refresh(current_user)
    return current_user


# ---------- Password reset ----------
# Two ways in (email link, texted code), one way to actually change the
# password. Both "forgot" endpoints always return the same generic message
# regardless of whether the account exists -- so a stranger poking at the
# API can't use it to find out which emails are registered.

@router.post("/password/forgot")
def forgot_password_email(body: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)):
    generic = {"message": "If an account exists for that email, a reset link has been sent."}
    user = db.query(models.User).filter(models.User.email == body.email).first()
    if not user:
        return generic

    token = secrets.token_urlsafe(32)
    user.reset_token = token
    user.reset_token_expires = datetime.datetime.utcnow() + datetime.timedelta(minutes=RESET_LINK_TTL_MINUTES)
    db.commit()

    reset_link = f"{settings.frontend_base_url}?reset_token={token}"
    try:
        emailer.send_reset_email(user.email, reset_link, token)
    except Exception as e:
        # Deliberately NOT the generic message here -- if email genuinely
        # isn't configured (or Gmail rejects the login), that's an admin-
        # facing setup problem, not something to hide from the requester.
        raise HTTPException(400, f"Couldn't send reset email: {e}")
    return generic


@router.post("/password/forgot-sms")
def forgot_password_sms(body: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)):
    generic = {"message": "If a verified phone number is on that account, a reset code has been texted to it."}
    user = db.query(models.User).filter(models.User.email == body.email).first()
    if not user or not user.phone_verified or not user.phone_number:
        return generic

    # Six digits, same shape as phone verification -- short enough to type
    # back in, unlike the emailed link's long token.
    code = f"{secrets.randbelow(10**6):06d}"
    user.reset_token = code
    user.reset_token_expires = datetime.datetime.utcnow() + datetime.timedelta(minutes=RESET_SMS_CODE_TTL_MINUTES)
    db.commit()

    try:
        otp.send_sms(user.phone_number, f"Your Chaos Tracker password reset code is {code}")
    except Exception as e:
        raise HTTPException(400, f"Couldn't send reset code: {e}")

    if settings.otp_provider == "mock":
        # Same dev-mode convenience as /phone/request's mock_code -- "mock"
        # never actually sends anything, so there'd be no other way to see it.
        generic["mock_code"] = code
    return generic


@router.post("/password/change")
def change_password(
    body: schemas.ChangePasswordRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The 'Change' button under Account security in Settings -- separate
    from the forgot-password flow above since the user is already logged in
    and proves ownership with their current password, not an emailed/texted
    token."""
    if not security.verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(400, "Current password is incorrect.")
    if body.current_password == body.new_password:
        raise HTTPException(400, "New password must be different from your current password.")

    current_user.password_hash = security.hash_password(body.new_password)
    db.commit()
    return {"message": "Password changed."}


@router.post("/password/reset", response_model=schemas.TokenResponse)
def reset_password(body: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.reset_token == body.token).first()
    if not user or not user.reset_token_expires or datetime.datetime.utcnow() > user.reset_token_expires:
        raise HTTPException(400, "That reset link or code is invalid or has expired -- request a new one.")

    user.password_hash = security.hash_password(body.new_password)
    user.reset_token = None
    user.reset_token_expires = None
    db.commit()
    db.refresh(user)

    # Log them straight in -- there's no reason to make someone who just
    # proved account ownership go type their new password a second time.
    token = security.create_access_token(user.id)
    return schemas.TokenResponse(access_token=token, user=user)
