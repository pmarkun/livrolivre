from __future__ import annotations

import json
import sqlite3
import time

from .books import BOOKS, Book
from .settings import DATA_DIR, DB_PATH, UPLOAD_DIR


def now() -> int:
    return int(time.time())


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                config_json TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL DEFAULT 1,
                author_name TEXT NOT NULL DEFAULT '',
                city TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL DEFAULT '',
                visibility TEXT NOT NULL CHECK (visibility IN ('public', 'private')),
                status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'hidden')) DEFAULT 'pending',
                media_type TEXT,
                media_path TEXT,
                media_original_name TEXT,
                image_path TEXT,
                image_original_name TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                user_agent TEXT NOT NULL DEFAULT '',
                ip_hash TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (book_id) REFERENCES books(id)
            )
            """
        )
        migrate_submissions(conn)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_public ON submissions (book_id, visibility, status, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_mod ON submissions (book_id, created_at)")
        sync_books(conn)


def migrate_submissions(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(submissions)").fetchall()}
    additions = {
        "book_id": "ALTER TABLE submissions ADD COLUMN book_id INTEGER NOT NULL DEFAULT 1",
        "media_type": "ALTER TABLE submissions ADD COLUMN media_type TEXT",
        "media_path": "ALTER TABLE submissions ADD COLUMN media_path TEXT",
        "media_original_name": "ALTER TABLE submissions ADD COLUMN media_original_name TEXT",
        "image_path": "ALTER TABLE submissions ADD COLUMN image_path TEXT",
        "image_original_name": "ALTER TABLE submissions ADD COLUMN image_original_name TEXT",
    }
    for column, sql in additions.items():
        if column not in columns:
            conn.execute(sql)
    conn.execute(
        """
        UPDATE submissions
        SET media_type = COALESCE(media_type, CASE WHEN image_path IS NOT NULL THEN 'image' END),
            media_path = COALESCE(media_path, image_path),
            media_original_name = COALESCE(media_original_name, image_original_name)
        WHERE image_path IS NOT NULL OR media_path IS NOT NULL
        """
    )


def sync_books(conn: sqlite3.Connection) -> None:
    timestamp = now()
    for book in BOOKS.values():
        payload = json.dumps(
            {
                "slug": book.slug,
                "title": book.title,
                "short_title": book.short_title,
                "badge": book.badge,
                "hero_image": book.hero_image,
                "cover_image": book.cover_image,
                "theme": book.theme,
                "copy": book.copy,
                "subdomains": list(book.subdomains),
            },
            ensure_ascii=False,
        )
        conn.execute(
            """
            INSERT INTO books (slug, title, config_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET title = excluded.title,
                config_json = excluded.config_json, updated_at = excluded.updated_at
            """,
            (book.slug, book.title, payload, timestamp, timestamp),
        )


def book_id(conn: sqlite3.Connection, slug: str) -> int:
    row = conn.execute("SELECT id FROM books WHERE slug = ?", (slug,)).fetchone()
    if not row:
        raise ValueError("Livro nao encontrado.")
    return int(row["id"])


def public_submissions(book: Book) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT s.* FROM submissions s
            JOIN books b ON b.id = s.book_id
            WHERE b.slug = ? AND s.visibility = 'public' AND s.status = 'approved'
            ORDER BY s.created_at DESC LIMIT 48
            """,
            (book.slug,),
        ).fetchall()


def admin_submissions() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT s.*, b.slug AS book_slug, b.title AS book_title
            FROM submissions s
            JOIN books b ON b.id = s.book_id
            ORDER BY s.created_at DESC LIMIT 500
            """
        ).fetchall()
