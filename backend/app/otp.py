"""
Phone verification. Three providers:

- "mock" (default): no SMS is sent. We generate a fixed code (123456), store
  it on the user row, and compare it ourselves when they confirm. Zero
  third-party accounts needed -- good for building/testing the flow.

- "textbelt": real SMS via textbelt.com's free tier -- zero signup, zero
  card, just a plain HTTP POST. The catch: the free tier (key="textbelt") is
  limited to 1 text per day, shared across everyone using that public key,
  so it can occasionally fail with a quota error if it's had heavy use that
  day. Get your own paid key at textbelt.com if you outgrow that.

- "twilio": real SMS via Twilio's plain Messaging API. Needs a Twilio
  account, and (as of when this was written) Twilio requires an
  upgraded/funded account even to claim a phone number, not just to use the
  fancier Verify product -- see the README for cost details if you go this
  route instead.

Both real providers generate our own random 6-digit code (same shape as
mock, just randomized) and text it, then we compare it locally when the user
submits it back. Neither hands code-generation/checking off to the SMS
provider the way Twilio's separate Verify product would -- that's a
deliberate simplification so all three providers share the same check_otp()
logic.

Setup for Textbelt (fastest path to a real text with zero signup):
  1. Set OTP_PROVIDER=textbelt in .env. That's it -- the default
     TEXTBELT_API_KEY is already the public free-tier key.
  2. Restart the server. You get 1 real free text per day this way.

Setup for Twilio (see README "Going to real phone verification" for the
account-upgrade / cost details):
  1. pip install twilio
  2. Create a Twilio account, get a phone number (requires an upgraded/funded
     account), and copy your Account SID + Auth Token from the dashboard.
  3. Set in .env: OTP_PROVIDER=twilio, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
     TWILIO_FROM_NUMBER (E.164 format, e.g. +15551234567).
  4. Restart the server. On a trial account, Twilio can only text numbers
     you've verified under Phone Numbers -> Verified Caller IDs.
"""
import datetime
import secrets

import httpx

from app.config import settings

MOCK_CODE = "123456"
OTP_TTL_MINUTES = 10
TEXTBELT_URL = "https://textbelt.com/text"


def _generate_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def _twilio_client():
    # Imported lazily so `twilio` doesn't need to be installed at all unless
    # you've actually switched OTP_PROVIDER to "twilio".
    from twilio.rest import Client

    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


def send_sms(phone_number: str, message: str) -> None:
    """Low-level "just send this text" -- used by send_otp (phone
    verification) below, and separately by password-reset SMS codes (see
    app/routers/auth.py's /password/forgot-sms). Same three providers, same
    config, just without the verification-specific code generation/storage
    baked in. No-ops under "mock" -- there's no real phone to text, so the
    caller is responsible for surfacing the code some other way (e.g. the
    dev-mode mock_code echoed in API responses)."""
    if settings.otp_provider == "mock":
        return

    if settings.otp_provider == "textbelt":
        resp = httpx.post(
            TEXTBELT_URL,
            data={"phone": phone_number, "message": message, "key": settings.textbelt_api_key},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            # e.g. "Exceeded quota for this phone number" once the free
            # tier's 1/day is used up, or a malformed phone number.
            raise RuntimeError(data.get("error", "Textbelt rejected the request for an unknown reason."))
        return

    if settings.otp_provider == "twilio":
        if not (settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from_number):
            raise RuntimeError(
                "OTP_PROVIDER=twilio but TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / "
                "TWILIO_FROM_NUMBER aren't all set in .env."
            )
        _twilio_client().messages.create(body=message, from_=settings.twilio_from_number, to=phone_number)
        return

    raise NotImplementedError(f"OTP provider '{settings.otp_provider}' is not wired up yet")


def send_otp(phone_number: str) -> tuple[str, datetime.datetime]:
    """Sends a verification code to phone_number. Returns (code, expires_at)
    -- for every provider here, `code` is something WE generated and must
    store ourselves in order to check it later (see check_otp)."""
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=OTP_TTL_MINUTES)

    if settings.otp_provider == "mock":
        return MOCK_CODE, expires_at

    code = _generate_code()
    send_sms(phone_number, f"Your Chaos Tracker verification code is {code}")
    return code, expires_at


def check_otp(phone_number: str, submitted_code: str, stored_code: str | None) -> bool:
    """Checks a user-submitted code. Every provider here compares against
    `stored_code` (the code send_otp() generated and we saved on the user
    row) -- none of them hand code generation/checking off to the SMS
    provider, so we're always the source of truth. `phone_number` is accepted
    for symmetry with a possible future Verify-style provider that would
    check with the provider directly instead."""
    if settings.otp_provider in ("mock", "textbelt", "twilio"):
        return stored_code is not None and submitted_code == stored_code

    raise NotImplementedError(f"OTP provider '{settings.otp_provider}' is not wired up yet")
