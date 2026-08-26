import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.phone import normalize_phone_number

Category = Literal["accident", "shooting", "protest", "fire", "weather", "other"]
Severity = Literal["low", "med", "high"]
Impact = Literal["moderate", "high", "elevated"]


# ---------- Auth ----------
class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class PhoneRequest(BaseModel):
    phone_number: str = Field(min_length=7, max_length=32)

    @field_validator("phone_number")
    @classmethod
    def _normalize(cls, v: str) -> str:
        # Runs before this number is ever stored or compared -- see
        # app/phone.py for why this matters for the one-phone-per-account
        # limit specifically (it'd be trivial to bypass otherwise by just
        # typing the same real number with different punctuation).
        return normalize_phone_number(v)


class PhoneConfirm(BaseModel):
    code: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=64)
    new_password: str = Field(min_length=8)


class ChangePasswordRequest(BaseModel):
    # For a logged-in user changing their password from account settings --
    # distinct from ResetPasswordRequest, which is for someone who's locked
    # out and proves ownership via an emailed/texted token instead.
    current_password: str
    new_password: str = Field(min_length=8)


# ---------- User ----------
class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    phone_verified: bool
    trust_score: int
    show_username_on_reports: bool
    precise_location: bool
    home_location: Optional[str]
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class HomeLocationUpdate(BaseModel):
    # Free-text, self-reported, purely for aggregate data insights -- not
    # geocoded and not used to set anyone's map center or default location.
    home_location: str = Field(min_length=2, max_length=200)


class UserProfileStats(BaseModel):
    reports_submitted: int
    verified_accuracy_pct: float
    corroborations_given: int
    trust_score: int


# ---------- Incidents ----------
class IncidentCreate(BaseModel):
    category: Category
    severity: Severity = "med"
    description: str = Field(min_length=3, max_length=2000)
    lat: float
    lng: float
    image_url: Optional[str] = None
    gif_url: Optional[str] = None


class IncidentOut(BaseModel):
    id: int
    category: Category
    severity: Severity
    description: str
    lat: float
    lng: float
    verified: bool
    confirms: int
    denies: int
    reporter_id: Optional[int]
    image_url: Optional[str]
    gif_url: Optional[str]
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class HexCell(BaseModel):
    h3_index: str
    lat: float
    lng: float
    boundary: list[list[float]]  # [[lat,lng], ...] polygon vertices
    count: int
    density: float  # 0..1, normalized against the busiest cell in this response


# ---------- Comments & reactions ----------
class CommentCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    image_url: Optional[str] = None
    gif_url: Optional[str] = None


class CommentUpdate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class ReactionIn(BaseModel):
    emoji: str = Field(min_length=1, max_length=8)


class CommentOut(BaseModel):
    id: int
    incident_id: int
    author_id: int
    author_username: str
    text: str
    image_url: Optional[str]
    gif_url: Optional[str]
    created_at: datetime.datetime
    edited_at: Optional[datetime.datetime]
    reactions: dict[str, int]  # emoji -> count

    class Config:
        from_attributes = True


# ---------- Verification ----------
class VoteRequest(BaseModel):
    confirm: bool


class VoteResult(BaseModel):
    incident_id: int
    confirms: int
    denies: int
    verified: bool


# ---------- Events ----------
class EventCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    icon: str = "📅"
    description: str
    impact: Impact = "moderate"
    lat: float
    lng: float
    starts_at: datetime.datetime
    ends_at: Optional[datetime.datetime] = None


class EventOut(BaseModel):
    id: int
    name: str
    icon: str
    description: str
    impact: Impact
    lat: float
    lng: float
    starts_at: datetime.datetime
    ends_at: Optional[datetime.datetime]
    thumbs_up: int
    thumbs_down: int
    comment_count: int

    class Config:
        from_attributes = True


# ---------- Event reactions & comments ----------
class EventReactionIn(BaseModel):
    is_up: bool


class EventReactionResult(BaseModel):
    event_id: int
    thumbs_up: int
    thumbs_down: int
    my_reaction: Optional[bool]  # true=up, false=down, null=no active reaction


class EventCommentCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    image_url: Optional[str] = None
    gif_url: Optional[str] = None


class EventCommentUpdate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class EventCommentOut(BaseModel):
    id: int
    event_id: int
    author_id: int
    author_username: str
    text: str
    image_url: Optional[str]
    gif_url: Optional[str]
    created_at: datetime.datetime
    edited_at: Optional[datetime.datetime]

    class Config:
        from_attributes = True


# ---------- Place search ----------
class PlaceResult(BaseModel):
    label: str
    lat: float
    lng: float


class PlaceSearchResponse(BaseModel):
    results: list[PlaceResult]


# ---------- Area insights ----------
class AreaInsights(BaseModel):
    lat: float
    lng: float
    radius_km: float
    reports_last_6mo: int
    reports_prior_6mo: int
    trend_pct: float  # positive = rise, negative = decrease
    reports_30d: int
    verified_rate_pct: float
    demographics_available: bool = False
    note: str = "Population/income/area-size come from the Census ACS integration -- not wired up yet, see README."


# ---------- Chat ----------
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    lat: Optional[float] = None
    lng: Optional[float] = None


class ToolCallRecord(BaseModel):
    tool: str
    input: dict
    output: dict


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[ToolCallRecord]


TokenResponse.model_rebuild()
