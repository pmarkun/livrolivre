from __future__ import annotations

import hashlib
import secrets

from .books import Book
from .forms import UploadedFile
from .settings import ALLOWED_MEDIA_TYPES, MAX_UPLOAD_BYTES, UPLOAD_DIR, upload_limit_mb


def save_media(book: Book, upload: UploadedFile | None) -> tuple[str | None, str | None, str | None]:
    if not upload or not upload.filename or not upload.data:
        return None, None, None
    kind_ext = ALLOWED_MEDIA_TYPES.get(upload.content_type)
    if not kind_ext:
        raise ValueError("Envie imagem, video ou audio em um formato comum.")
    media_type, ext = kind_ext
    if len(upload.data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"O arquivo ficou grande demais. O limite atual e {upload_limit_mb()} MB.")
    digest = hashlib.sha256(upload.data + secrets.token_bytes(16)).hexdigest()[:24]
    filename = f"{book.slug}/{digest}{ext}"
    target = UPLOAD_DIR / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(upload.data)
    return media_type, filename, upload.filename[:160]
