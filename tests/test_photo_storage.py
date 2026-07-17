"""Tests for photo upload validation and storage."""

import io

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image


def _upload(data: bytes, content_type: str, filename: str = "catch.jpg") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(data), headers={"content-type": content_type})


def _jpeg_bytes(size=(50, 50), color=(60, 110, 70)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _photos_dir(tmp_path, monkeypatch):
    from src.services import photo_storage
    monkeypatch.setattr(photo_storage, "PHOTOS_DIR", tmp_path / "photos")
    return tmp_path / "photos"


def test_save_valid_jpeg_writes_file_and_returns_url():
    from src.services.photo_storage import save_photo

    result = save_photo(_upload(_jpeg_bytes(), "image/jpeg"))
    assert result["url"].startswith("/photos/")
    assert result["url"].endswith(".jpg")
    from pathlib import Path
    assert Path(result["path"]).exists()


def test_save_png_uses_png_extension():
    from src.services.photo_storage import save_photo

    buf = io.BytesIO()
    Image.new("RGB", (50, 50)).save(buf, format="PNG")
    result = save_photo(_upload(buf.getvalue(), "image/png", filename="catch.png"))
    assert result["url"].endswith(".png")


def test_rejects_unsupported_content_type():
    from src.services.photo_storage import save_photo

    with pytest.raises(HTTPException) as exc:
        save_photo(_upload(b"not an image", "application/pdf"))
    assert exc.value.status_code == 400


def test_rejects_corrupt_image_bytes():
    from src.services.photo_storage import save_photo

    with pytest.raises(HTTPException) as exc:
        save_photo(_upload(b"\xff\xd8\xff totally not a real jpeg", "image/jpeg"))
    assert exc.value.status_code == 400


def test_rejects_empty_upload():
    from src.services.photo_storage import save_photo

    with pytest.raises(HTTPException) as exc:
        save_photo(_upload(b"", "image/jpeg"))
    assert exc.value.status_code == 400


def test_rejects_oversized_photo():
    from src.services.photo_storage import MAX_PHOTO_BYTES, save_photo

    oversized = _jpeg_bytes() + b"\x00" * MAX_PHOTO_BYTES
    with pytest.raises(HTTPException) as exc:
        save_photo(_upload(oversized, "image/jpeg"))
    assert exc.value.status_code == 400
    assert "10MB" in exc.value.detail


def test_filenames_are_unguessable_uuids_not_client_supplied():
    from src.services.photo_storage import save_photo

    result = save_photo(_upload(_jpeg_bytes(), "image/jpeg", filename="../../etc/passwd.jpg"))
    assert "etc" not in result["url"]
    assert "passwd" not in result["url"]
