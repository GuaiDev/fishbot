"""Catch photo storage — saves uploaded photo files to the Railway persistent volume.

Files land under DATA_DIR/photos, alongside fishing.db, keyed by an unguessable
UUID filename. Served back out via the /photos StaticFiles mount in src/api/main.py.
"""

import io
import os
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from pillow_heif import register_heif_opener

register_heif_opener()  # lets Image.open() decode iPhone HEIC/HEIF photos

PHOTOS_DIR = Path(os.environ.get("DATA_DIR", "data")) / "photos"

MAX_PHOTO_BYTES = 10 * 1024 * 1024  # 10MB

_CONTENT_TYPE_TO_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
    "image/heif": "heif",
}


def save_photo(upload: UploadFile, *, public_base: str = "/photos") -> dict:
    """Validate and persist an uploaded photo. Returns {"path": str, "url": str}.

    Raises HTTPException(400) for anything that isn't a real, reasonably-sized image.
    """
    ext = _CONTENT_TYPE_TO_EXT.get((upload.content_type or "").lower())
    if not ext:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported photo type: {upload.content_type}. Use JPEG, PNG, WEBP, or HEIC.",
        )

    data = upload.file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=400, detail="Photo exceeds 10MB limit.")
    if not data:
        raise HTTPException(status_code=400, detail="Empty photo upload.")

    try:
        Image.open(io.BytesIO(data)).verify()
    except UnidentifiedImageError as e:
        raise HTTPException(status_code=400, detail="File is not a valid image.") from e

    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{ext}"
    dest = PHOTOS_DIR / filename
    dest.write_bytes(data)

    return {"path": str(dest), "url": f"{public_base}/{filename}"}
