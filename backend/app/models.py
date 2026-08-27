import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
)
from sqlalchemy.orm import relationship

from app.database import Base


def utcnow():
    return datetime.datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(40), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    phone_number = Column(String(32), nullable=True)
    phone_verified = Column(Boolean, default=False, nullable=False)
    # mock OTP state -- lives on the user row so we don't need a whole extra table for the MVP
    pending_otp_code = Column(String(10), nullable=True)
    pending_otp_expires = Column(DateTime, nullable=True)

    trust_score = Column(Integer, default=50, nullable=False)
    show_username_on_reports = Column(Boolean, default=True, nullable=False)
    precise_location = Column(Boolean, default=False, nullable=False)
    # Free-text, self-reported "where do you live" -- optional, collected
    # purely for aggregate data insights (e.g. where the user base actually
    # is), never geocoded and never used to set anyone's map center.
    home_location = Column(String(200), nullable=True)

    # Password reset -- shared by both the emailed link (a long random
    # token) and the texted code (a short 6-digit one); whichever the user
    # submits to /auth/password/reset, it's just a string compared against
    # this column. Cleared once used or once a new one is issued.
    reset_token = Column(String(64), nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=utcnow, nullable=False)

    incidents = relationship("Incident", back_populates="reporter")
    comments = relationship("Comment", back_populates="author")


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    reporter_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    category = Column(String(20), nullable=False)  # accident | shooting | protest | fire | weather | other
    severity = Column(String(10), default="med", nullable=False)  # low | med | high
    description = Column(Text, nullable=False)

    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)

    verified = Column(Boolean, default=False, nullable=False)
    confirms = Column(Integer, default=0, nullable=False)
    denies = Column(Integer, default=0, nullable=False)

    image_url = Column(String(500), nullable=True)
    gif_url = Column(String(500), nullable=True)

    created_at = Column(DateTime, default=utcnow, nullable=False, index=True)

    reporter = relationship("User", back_populates="incidents")
    comments = relationship("Comment", back_populates="incident", cascade="all, delete-orphan")
    votes = relationship("VerificationVote", back_populates="incident", cascade="all, delete-orphan")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    text = Column(Text, nullable=False)
    image_url = Column(String(500), nullable=True)
    gif_url = Column(String(500), nullable=True)

    created_at = Column(DateTime, default=utcnow, nullable=False)
    edited_at = Column(DateTime, nullable=True)

    incident = relationship("Incident", back_populates="comments")
    author = relationship("User", back_populates="comments")
    reactions = relationship("Reaction", back_populates="comment", cascade="all, delete-orphan")


class Reaction(Base):
    __tablename__ = "reactions"
    __table_args__ = (UniqueConstraint("comment_id", "user_id", "emoji", name="uq_reaction_once"),)

    id = Column(Integer, primary_key=True, index=True)
    comment_id = Column(Integer, ForeignKey("comments.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    emoji = Column(String(8), nullable=False)

    comment = relationship("Comment", back_populates="reactions")


class VerificationVote(Base):
    __tablename__ = "verification_votes"
    __table_args__ = (UniqueConstraint("incident_id", "user_id", name="uq_one_vote_per_user"),)

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    confirm = Column(Boolean, nullable=False)  # True = confirm, False = deny
    created_at = Column(DateTime, default=utcnow, nullable=False)

    incident = relationship("Incident", back_populates="votes")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    icon = Column(String(8), default="\U0001F4C5", nullable=False)
    description = Column(Text, nullable=False)
    impact = Column(String(12), default="moderate", nullable=False)  # moderate | high | elevated

    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)

    starts_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=True)

    # --- AI-discovered event fields (see app/discovery.py) ---
    # All nullable/defaulted so manually-created events (the original
    # EventCreate flow) are unaffected.
    venue_name = Column(String(160), nullable=True)
    expected_attendance = Column(Integer, nullable=True)
    chaos_score = Column(Integer, nullable=True)  # 0-100 -- the "chaos meter", finer-grained than impact
    source_url = Column(String(500), nullable=True)  # real listing this was found from, if AI-discovered
    ai_generated = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=utcnow, nullable=False)

    reactions = relationship("EventReaction", back_populates="event", cascade="all, delete-orphan")
    event_comments = relationship("EventComment", back_populates="event", cascade="all, delete-orphan")


class NewsReport(Base):
    """Real local news items (accidents, fires, crime, etc.) discovered via
    AI web search -- see app/discovery.py. Deliberately NOT the Incident
    table: these are secondhand, unverified-by-us news summaries, not
    firsthand user reports, and mixing them into Incident would let a news
    blurb accumulate confirm/deny votes and a trust score exactly like a
    real eyewitness report. Kept as its own read-only-to-users table so the
    frontend can render them in a visibly distinct way."""
    __tablename__ = "news_reports"

    id = Column(Integer, primary_key=True, index=True)
    headline = Column(String(300), nullable=False)
    summary = Column(Text, nullable=False)
    category = Column(String(20), nullable=False)  # accident | shooting | protest | fire | weather | other

    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)

    source_name = Column(String(120), nullable=False)
    source_url = Column(String(500), nullable=False, unique=True)  # dedup key across discovery runs
    published_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=utcnow, nullable=False)


class EventReaction(Base):
    """Thumbs up/down on an event -- one vote per user, switchable, distinct
    from the emoji Reaction table above (that one's for comments and allows
    any number of different emoji at once; this one is a single up-or-down
    opinion per user per event)."""
    __tablename__ = "event_reactions"
    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_one_reaction_per_user_per_event"),)

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_up = Column(Boolean, nullable=False)  # True = thumbs up, False = thumbs down
    created_at = Column(DateTime, default=utcnow, nullable=False)

    event = relationship("Event", back_populates="reactions")


class EventComment(Base):
    """Open comments on an event, for users to share their opinions.
    Deliberately its own table rather than reusing Comment (which has a
    NOT NULL incident_id) -- that avoids an ALTER TABLE migration on the
    existing comments table, which SQLite (and our current create_all-only
    schema management, see README) can't do safely in place."""
    __tablename__ = "event_comments"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    text = Column(Text, nullable=False)
    image_url = Column(String(500), nullable=True)
    gif_url = Column(String(500), nullable=True)

    created_at = Column(DateTime, default=utcnow, nullable=False)
    edited_at = Column(DateTime, nullable=True)

    event = relationship("Event", back_populates="event_comments")
    author = relationship("User")
