"""
App configuration, loaded from environment variables (see .env.example).
Uses pydantic-settings so misconfiguration fails fast and loudly at startup
instead of causing a confusing error three requests later.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./chaos.db"
    secret_key: str = "change-me-to-a-long-random-string"
    access_token_expire_minutes: int = 10080  # 7 days
    otp_provider: str = "mock"  # "mock" | "textbelt" | "twilio"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:5500"

    # --- Textbelt (real SMS, zero signup) ---
    # Only needed when OTP_PROVIDER=textbelt. The default "textbelt" key is
    # Textbelt's public free-tier key: 1 free text per day, no account or
    # card needed at all. Get your own paid key at textbelt.com if you need
    # more than 1/day later -- just paste it here, no code changes needed.
    textbelt_api_key: str = "textbelt"

    # --- Twilio (real SMS phone verification, plain Messaging API) ---
    # Only needed when OTP_PROVIDER=twilio. account_sid and auth_token are on
    # the main console.twilio.com dashboard. from_number is a Twilio phone
    # number you own (Phone Numbers -> Manage -> Active Numbers), used as the
    # sender for the SMS. We generate/check the code ourselves -- see
    # app/otp.py for why (Twilio's fancier Verify product needs a
    # paid/upgraded account; this plain-SMS approach works on a trial).
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    # Unused by the current plain-SMS implementation -- kept for anyone who
    # upgrades their Twilio account and wants to switch to the Verify product
    # instead (see app/otp.py docstring).
    twilio_verify_service_sid: str = ""

    # How many independent "confirm" votes an incident needs before it flips to verified.
    verification_threshold: int = 3

    # --- Comment photo/GIF uploads ---
    # Local-disk storage by default -- zero setup, zero cloud account needed.
    # For production, swap app/routers/uploads.py's save step for a boto3 put_object
    # call against S3 or Cloudflare R2 (no code changes needed anywhere else --
    # it still just returns a URL that goes in image_url/gif_url).
    upload_dir: str = "uploads"
    max_upload_mb: int = 8

    # --- AI chatbot ---
    # From https://platform.claude.com/settings/keys (Anthropic's console moved
    # here from console.anthropic.com). Leave blank to keep the /chat endpoint
    # disabled -- everything else in the app works without it.
    anthropic_api_key: str = ""
    # Check https://docs.claude.com/en/docs/about-claude/models for the current
    # model ID list -- this default may go stale.
    anthropic_model: str = "claude-sonnet-4-5"

    # --- Census migration data (used by the /chat tool get_county_migration) ---
    # Free key from https://api.census.gov/data/key_signup.html. Leave blank and
    # that one tool will just report itself unavailable rather than failing.
    census_api_key: str = ""

    # --- GIF search (Klipy) ---
    # Powers the in-app GIF picker on comments (search + tap, like
    # Instagram/WhatsApp) -- proxied through this backend so the key never
    # sits in the frontend's plain HTML file. Originally built on Google's
    # Tenor API, which Google shut down entirely on 2026-06-30 -- see
    # app/routers/gifs.py for the full story and why Klipy replaced it.
    # Free key: https://klipy.com/developers. Leave blank and the GIF
    # picker just shows "not configured" instead of failing.
    klipy_api_key: str = ""

    # --- Password reset email ---
    # Two options, checked in this order:
    #
    # 1. Resend (RESEND_API_KEY) -- sends over a normal HTTPS API call, so it
    #    works on Render's free tier. Free signup at resend.com, no card
    #    needed, 100 emails/day. Without verifying your own domain, Resend's
    #    shared "onboarding@resend.dev" sender can only deliver to the email
    #    address you signed up to Resend with -- fine for a single-user app
    #    like this one, since that'll be your own inbox. Leave
    #    resend_from_email blank to use that default sender.
    #
    # 2. Gmail SMTP (GMAIL_ADDRESS/GMAIL_APP_PASSWORD) -- works fine for local
    #    dev, but Render's free web services block all outbound SMTP traffic
    #    (ports 25/465/587) as of Sept 2025, so this option silently cannot
    #    work once deployed there -- keep it configured for running the
    #    backend locally, but use Resend for the deployed version. Gmail
    #    requires an "app password" rather than your normal login password:
    #    turn on 2-Step Verification at myaccount.google.com/security, then
    #    create one at myaccount.google.com/apppasswords.
    #
    # Leave all of these blank and the email-reset endpoint reports itself
    # unavailable (400) instead of failing -- the SMS-based reset (see
    # app/otp.py) still works independently of this.
    resend_api_key: str = ""
    resend_from_email: str = "onboarding@resend.dev"
    gmail_address: str = ""
    gmail_app_password: str = ""

    # --- Photo/GIF storage (Cloudflare R2) ---
    # Leave all four blank to keep saving uploads to local disk (upload_dir
    # above) -- fine for local dev, but most hosting platforms (including
    # Render's free tier) wipe local disk on every redeploy/restart, so
    # anything a user uploaded would eventually vanish. R2 is S3-compatible
    # storage with a generous free tier (10GB, zero egress fees) -- once
    # these are set, app/routers/uploads.py switches to writing there
    # instead, and nothing else in the app needs to change (it still just
    # gets back a URL for image_url/gif_url).
    #
    # Setup: cloudflare.com dashboard -> R2 -> Create bucket (any name) ->
    # Settings -> make it public (enables the dev subdomain URL, or attach a
    # custom domain) -> note the public URL. Then R2 -> Manage API tokens ->
    # Create API token (Object Read & Write, scoped to that bucket) -> note
    # the Account ID, Access Key ID, and Secret Access Key it shows you
    # (the secret is only shown once).
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = ""
    r2_public_base_url: str = ""  # e.g. https://pub-xxxx.r2.dev or your custom domain, no trailing slash

    # Where the frontend actually lives, so a password-reset email/SMS can
    # build a real clickable link -- e.g. the URL your Live Server serves
    # chaos-tracker-live.html from. Update this once you deploy anywhere
    # other than your own machine.
    frontend_base_url: str = "http://127.0.0.1:5500/chaos-tracker-live.html"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
