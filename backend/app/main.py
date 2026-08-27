import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from app.config import settings
from app.database import Base, engine
from app.routers import areas, auth, chat, comments, events, gifs, incidents, news, uploads, users, verify

# MVP-simple schema management: create any missing tables on startup.
# Once the schema stabilizes, switch to Alembic migrations instead of this
# (create_all never alters existing tables, so it won't help with schema
# changes down the line) -- see README "Next: real migrations".
Base.metadata.create_all(bind=engine)


def _ensure_column(table: str, column: str, ddl_type: str):
    """Patches around create_all()'s one real limitation: it creates missing
    TABLES but never adds columns to a table that already exists. Without
    this, someone with an existing chaos.db from before User.home_location
    was added would hit a hard "no such column" error on their very next
    request. Both SQLite and Postgres support plain ADD COLUMN directly, so
    this stays a one-line, idempotent, additive migration -- see the note
    above for when to graduate to real Alembic migrations instead.

    ddl_type must be a type valid on BOTH engines, since this same code runs
    against SQLite locally and Postgres (Supabase) once deployed -- e.g.
    TIMESTAMP, not SQLite-only DATETIME (Postgres has no such type)."""
    existing = {c["name"] for c in inspect(engine).get_columns(table)}
    if column not in existing:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


_ensure_column("users", "home_location", "VARCHAR(200)")
_ensure_column("users", "reset_token", "VARCHAR(64)")
_ensure_column("users", "reset_token_expires", "TIMESTAMP")
_ensure_column("incidents", "image_url", "VARCHAR(500)")
_ensure_column("incidents", "gif_url", "VARCHAR(500)")
_ensure_column("events", "venue_name", "VARCHAR(160)")
_ensure_column("events", "expected_attendance", "INTEGER")
_ensure_column("events", "chaos_score", "INTEGER")
_ensure_column("events", "source_url", "VARCHAR(500)")
_ensure_column("events", "ai_generated", "BOOLEAN NOT NULL DEFAULT FALSE")

app = FastAPI(
    title="Chaos Tracker API",
    description="Backend for the Chaos Tracker map: incidents, comments, verification voting, events, and area insights.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(incidents.router)
app.include_router(comments.router)
app.include_router(verify.router)
app.include_router(events.router)
app.include_router(news.router)
app.include_router(areas.router)
app.include_router(chat.router)
app.include_router(uploads.router)
app.include_router(gifs.router)

# Serves uploaded comment photos/GIFs back out (see app/routers/uploads.py).
# Mounted at /media, not /uploads, so it doesn't collide with the POST
# /uploads route above -- one path takes files in, a different one serves
# them back out.
os.makedirs(settings.upload_dir, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.upload_dir), name="media")


@app.get("/")
def root():
    return {"status": "ok", "service": "chaos-tracker-api", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok"}
