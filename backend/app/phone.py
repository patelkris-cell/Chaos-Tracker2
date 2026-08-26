"""
Phone number normalization -- turns whatever format someone types (spaces,
dashes, parens, with or without a leading country code) into one consistent
"+1XXXXXXXXXX"-style string before it's ever stored or compared.

This matters specifically for the one-verified-phone-per-account limit (see
_phone_taken_by_someone_else in app/routers/auth.py): that check does a plain
string equality lookup, so without normalizing first, "+15555550123",
"15555550123", and "(555) 555-0123" -- the exact same real phone number --
would all be stored as different strings and the limit would do nothing. It
also happens to make the real SMS providers happier: Twilio's docs
specifically ask for E.164 format (see app/otp.py).

Deliberately hand-rolled instead of pulling in the `phonenumbers` package
(Google's libphonenumber port) -- this app is US-only for now (both the
Textbelt and Twilio setup instructions in app/otp.py assume a 10-digit US
number), so a full international parsing library would be a new dependency
for a problem this small. If the app ever needs real international numbers,
swap this for `phonenumbers.parse()` / `format_number(..., E164)` instead --
much more correct for non-US numbering plans (variable lengths, area code
rules, etc. that this function doesn't know about).
"""
import re


def normalize_phone_number(raw: str) -> str:
    """Raises ValueError with a user-facing message on anything that isn't
    recognizable as a US phone number. Safe to call from a pydantic
    field_validator -- FastAPI turns a ValueError there into a normal 422
    the frontend already knows how to show nicely (see FIELD_LABELS /
    friendlyErrorMessage in the frontend's api() helper)."""
    digits = re.sub(r"[^\d+]", "", raw or "")  # strip spaces, dashes, parens, dots
    has_plus = digits.startswith("+")
    digits_only = digits.lstrip("+")

    if has_plus and len(digits_only) == 11 and digits_only.startswith("1"):
        return "+" + digits_only
    if not has_plus and len(digits_only) == 10:
        return "+1" + digits_only
    if not has_plus and len(digits_only) == 11 and digits_only.startswith("1"):
        return "+" + digits_only

    raise ValueError("Enter a valid US phone number, e.g. (555) 555-0123 or +15555550123.")
