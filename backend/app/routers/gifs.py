"""
Klipy GIF search -- powers the in-app GIF picker on comments (search, tap to
pick), the same idea as Instagram/WhatsApp's built-in GIF search, instead of
users uploading their own GIF files.

Originally built against Google's Tenor API, which Google shut down entirely
on 2026-06-30 (confirmed via news coverage 2026-08-26 -- it broke GIF
pickers across Discord, WhatsApp, X, and Bluesky too, not just this app).
Switched to Klipy: founded by ex-Tenor engineers specifically as a
replacement, free tier, instant signup with no approval wait (unlike
Giphy, whose production keys need manual review that can take days-weeks).

Proxied through this backend rather than called directly from the frontend
so the API key never has to live in the frontend's plain HTML file -- that
file is served straight to browsers, and anything in it is visible via
"View Source". Same reasoning as keeping the Anthropic/Census keys backend-
only (see app/config.py).

Response shape confirmed 2026-08-26 via a live curl against the real API
(this sandbox can't reach api.klipy.com directly, so this had to be
verified from the user's own machine -- same as the Census geocoder):

    {"result": true, "data": {"data": [
        {"id": ..., "title": "...", "file": {
            "hd": {"gif": {"url": "...", "width":.., "height":.., "size":..}, "webp": {...}, "jpg": {...}, "mp4": {...}, "webm": {...}},
            "md": {...same shape...}, "sm": {...}, "xs": {...}
        }, "tags": [], "type": "gif", "blur_preview": "data:..."},
        ...
    ], "current_page": 1, "per_page": 5, "has_next": true, "meta": {...}}}

So each item nests by SIZE first (hd/md/sm/xs), then by FORMAT (gif/webp/
jpg/mp4/webm) -- not the flat "files.gif"/"files.preview" shape guessed at
before this was verified. "md" is used for the actual gif_url (attached to
the comment); "xs" for preview_url (the small thumbnail in the picker
grid) since it's much smaller to load 24 of at once.

Returns Klipy's own CDN URLs directly (gif_url) -- these aren't downloaded
or re-hosted, they're just stored as a comment's gif_url exactly like an
uploaded file's /media/... URL would be (see app/routers/uploads.py). The
frontend's mediaUrl() helper already leaves absolute URLs untouched, so no
frontend changes were needed there.

Free key: sign up at https://klipy.com/developers. Leave KLIPY_API_KEY
blank in .env and this endpoint reports itself unavailable (503) instead of
failing.
"""
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app import models
from app.config import settings
from app.deps import get_current_user

router = APIRouter(prefix="/gifs", tags=["gifs"])

KLIPY_SEARCH_URL_TEMPLATE = "https://api.klipy.com/api/v1/{key}/gifs/search"


def _size_url(file_sizes: dict, size: str, fmt: str = "gif") -> str | None:
    return ((file_sizes.get(size) or {}).get(fmt) or {}).get("url")


@router.get("/search")
def search_gifs(
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(24, ge=1, le=50),
    current_user: models.User = Depends(get_current_user),
):
    if not settings.klipy_api_key:
        raise HTTPException(503, "GIF search isn't configured yet -- add KLIPY_API_KEY to the backend .env.")

    try:
        resp = httpx.get(
            KLIPY_SEARCH_URL_TEMPLATE.format(key=settings.klipy_api_key),
            params={"q": q, "per_page": limit, "page": 1, "locale": "en_US"},
            timeout=6.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(502, f"GIF search failed: {e}")

    if not data.get("result"):
        # e.g. {"result": false, "errors": {"message": ["The provided API key is invalid."]}}
        message = ", ".join((data.get("errors") or {}).get("message", ["Unknown error."]))
        raise HTTPException(502, f"Klipy rejected the request: {message}")

    items = ((data.get("data") or {}).get("data")) or []

    results = []
    for item in items:
        file_sizes = item.get("file") or {}
        gif_url = _size_url(file_sizes, "md") or _size_url(file_sizes, "sm") or _size_url(file_sizes, "hd")
        preview_url = _size_url(file_sizes, "xs") or _size_url(file_sizes, "sm") or gif_url
        if not gif_url:
            continue
        results.append({
            "id": item.get("id"),
            "title": item.get("title", ""),
            "preview_url": preview_url,
            "gif_url": gif_url,
        })
    return {"results": results}
