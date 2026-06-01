from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BOOKS_DIR = ROOT / "books"
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = Path(os.environ.get("DATABASE_PATH", DATA_DIR / "livrolivre.sqlite3"))
DEFAULT_BOOK_SLUG = os.environ.get("DEFAULT_BOOK_SLUG", "detetive-chapeuzinho")
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(40 * 1024 * 1024)))
APP_SECRET = os.environ.get("APP_SECRET", "troque-este-segredo-no-railway")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "chapeuzinho")
SESSION_COOKIE = "ll_admin"

ALLOWED_MEDIA_TYPES = {
    "image/jpeg": ("image", ".jpg"),
    "image/png": ("image", ".png"),
    "image/webp": ("image", ".webp"),
    "image/gif": ("image", ".gif"),
    "video/mp4": ("video", ".mp4"),
    "video/webm": ("video", ".webm"),
    "video/quicktime": ("video", ".mov"),
    "audio/mpeg": ("audio", ".mp3"),
    "audio/mp4": ("audio", ".m4a"),
    "audio/wav": ("audio", ".wav"),
    "audio/webm": ("audio", ".webm"),
    "audio/ogg": ("audio", ".ogg"),
}
