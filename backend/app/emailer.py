"""
Password-reset emails via Gmail SMTP -- uses your own Gmail account rather
than a dedicated transactional email service (Resend, SendGrid, etc.), so
there's zero new account to sign up for. The catch: Gmail's SMTP won't
accept your normal login password, only a 16-character "app password" --
turn on 2-Step Verification at myaccount.google.com/security, then generate
one at myaccount.google.com/apppasswords, and put that in GMAIL_APP_PASSWORD
(not your real Gmail password).

This is a fine fit for an app at hobby/dev scale. Gmail SMTP has informal
sending-volume limits (roughly ~500/day) and no real deliverability
infrastructure (SPF/DKIM alignment, bounce handling, etc.) the way a
dedicated provider has -- if this app ever needs to reliably reach lots of
real users' inboxes, swap this module for Resend/SendGrid/SES. Nothing
outside this file needs to change: the caller (app/routers/auth.py) just
calls send_reset_email(to, link) and doesn't know how it was sent.
"""
import smtplib
from email.mime.text import MIMEText

from app.config import settings

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def send_reset_email(to_email: str, reset_link: str, token: str) -> None:
    if not (settings.gmail_address and settings.gmail_app_password):
        raise RuntimeError("Email isn't configured -- set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env.")

    body = (
        "Someone (hopefully you) requested a password reset for your Chaos Tracker account.\n\n"
        f"Reset it here: {reset_link}\n\n"
        "If that link doesn't open (e.g. \"this site can't be reached\" -- can happen if the app isn't\n"
        "running from where the link expects, or your email app won't open local links), open Chaos\n"
        "Tracker yourself, click \"Forgot password?\", then paste this code into the reset form instead:\n\n"
        f"    {token}\n\n"
        "This expires in 30 minutes. If you didn't request this, you can safely ignore this email --\n"
        "your password hasn't been changed."
    )
    msg = MIMEText(body)
    msg["Subject"] = "Reset your Chaos Tracker password"
    msg["From"] = settings.gmail_address
    msg["To"] = to_email

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
        server.starttls()
        server.login(settings.gmail_address, settings.gmail_app_password)
        server.sendmail(settings.gmail_address, [to_email], msg.as_string())
