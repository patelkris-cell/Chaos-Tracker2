"""
Password-reset emails, via either of two backends -- see app/config.py's
comment above resend_api_key for the full explanation of why there are two.

1. Resend (preferred, and the only one that works once deployed to Render's
   free tier): a plain HTTPS POST, no SMTP involved at all.
2. Gmail SMTP: fine for local dev, but Render's free web services block
   outbound SMTP entirely, so this option is a no-op in production there.

Nothing outside this file needs to know which one is active: the caller
(app/routers/auth.py) just calls send_reset_email(to, link, token) and
doesn't know or care how it was sent.
"""
import smtplib
from email.mime.text import MIMEText

import httpx

from app.config import settings

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
RESEND_URL = "https://api.resend.com/emails"


def _reset_email_body(reset_link: str, token: str) -> str:
    return (
        "Someone (hopefully you) requested a password reset for your Chaos Tracker account.\n\n"
        f"Reset it here: {reset_link}\n\n"
        "If that link doesn't open (e.g. \"this site can't be reached\" -- can happen if the app isn't\n"
        "running from where the link expects, or your email app won't open local links), open Chaos\n"
        "Tracker yourself, click \"Forgot password?\", then paste this code into the reset form instead:\n\n"
        f"    {token}\n\n"
        "This expires in 30 minutes. If you didn't request this, you can safely ignore this email --\n"
        "your password hasn't been changed."
    )


def _send_via_resend(to_email: str, reset_link: str, token: str) -> None:
    resp = httpx.post(
        RESEND_URL,
        headers={"Authorization": f"Bearer {settings.resend_api_key}"},
        json={
            "from": f"Chaos Tracker <{settings.resend_from_email}>",
            "to": [to_email],
            "subject": "Reset your Chaos Tracker password",
            "text": _reset_email_body(reset_link, token),
        },
        timeout=10.0,
    )
    if resp.status_code >= 400:
        # Surface Resend's own error message (e.g. the resend.dev sandbox's
        # "you can only send to your own address" 403) rather than a bare
        # status code -- it's directly actionable.
        raise RuntimeError(f"Resend API error {resp.status_code}: {resp.text}")


def _send_via_gmail(to_email: str, reset_link: str, token: str) -> None:
    if not (settings.gmail_address and settings.gmail_app_password):
        raise RuntimeError(
            "Email isn't configured -- set RESEND_API_KEY (recommended, works on Render's free "
            "tier), or GMAIL_ADDRESS and GMAIL_APP_PASSWORD (local dev only) in .env."
        )

    msg = MIMEText(_reset_email_body(reset_link, token))
    msg["Subject"] = "Reset your Chaos Tracker password"
    msg["From"] = settings.gmail_address
    msg["To"] = to_email

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
        server.starttls()
        server.login(settings.gmail_address, settings.gmail_app_password)
        server.sendmail(settings.gmail_address, [to_email], msg.as_string())


def send_reset_email(to_email: str, reset_link: str, token: str) -> None:
    if settings.resend_api_key:
        _send_via_resend(to_email, reset_link, token)
    else:
        _send_via_gmail(to_email, reset_link, token)
