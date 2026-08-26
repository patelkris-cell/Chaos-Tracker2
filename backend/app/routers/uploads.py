"""
Photo/GIF uploads for comments and incident reports.

Two storage backends, chosen automatically based on whether R2 is
configured (see the R2_* settings in app/config.py):

- Local disk (settings.upload_dir), served back via a StaticFiles mount at
  /media (see app/main.py) -- zero cloud account needed, works immediately.
  This is the default, and what local dev uses. The catch: most hosting
  platforms (including Render's free tier) wipe local disk on every
  redeploy/restart, so anything uploaded here eventually disappears once
  deployed.
- Cloudflare R2 (S3-compatible), once R2_ACCOUNT_ID / R2_ACCESS_KEY_ID /
  R2_SECRET_ACCESS_KEY / R2_BUCKET_NAME / R2_PUBLIC_BASE_URL are all set --
  persistent regardless of redeploys.

Either way the response shape (`{"url": ...}`) is the only thing the
frontend depends on -- local disk returns a relative `/media/...` path,
R2 returns a full `https://...` URL, and the frontend's mediaUrl() helper
already leaves absolute URLs untouched (same trick already used for Klipy's
GIF CDN URLs), so nothing else in the app needs to know or care which
backend actually served a given upload.
"""
import os
import secrets

import boto3
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app import models
from app.config import settings
from app.deps import get_current_user

router = APIRouter(prefix="/uploads", tags=["uploads"])


def _r2_configured() -> bool:
    return bool(
        settings.r2_account_id
        and settings.r2_access_key_id
        and settings.r2_secret_access_key
        and settings.r2_bucket_name
        and settings.r2_public_base_url
    )


def _r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )

# Deliberately narrow allowlist -- comments only ever need still images or
# GIFs, and trusting the browser-supplied content_type for anything wider
# (e.g. video, or an open-ended extension) invites uploading arbitrary files.
ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


@router.post("")
async def upload_file(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            400,
            f"Unsupported file type '{file.content_type}'. Allowed: "
            + ", ".join(sorted(ALLOWED_CONTENT_TYPES)),
        )

    contents = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(400, f"File too large -- max {settings.max_upload_mb}MB.")
    if not contents:
        raise HTTPException(400, "Empty file.")

    # Random filename, not the user-supplied one -- avoids path traversal and
    # filename collisions, and doesn't leak the uploader's original filename.
    filename = f"{secrets.token_hex(16)}{ALLOWED_CONTENT_TYPES[file.content_type]}"

    if _r2_configured():
        try:
            _r2_client().put_object(
                Bucket=settings.r2_bucket_name,
                Key=filename,
                Body=contents,
                ContentType=file.content_type,
            )
        except Exception as e:
            raise HTTPException(502, f"Couldn't upload to storage: {e}")
        url = f"{settings.r2_public_base_url.rstrip('/')}/{filename}"
    else:
        os.makedirs(settings.upload_dir, exist_ok=True)
        with open(os.path.join(settings.upload_dir, filename), "wb") as f:
            f.write(contents)
        url = f"/media/{filename}"

    return {"url": url, "content_type": file.content_type, "size_bytes": len(contents)}
