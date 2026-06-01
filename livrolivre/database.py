from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

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


def storage_status() -> dict[str, object]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    writable = False
    probe = DATA_DIR / ".write-test"
    try:
        probe.write_text("ok", encoding="utf-8")
        writable = probe.read_text(encoding="utf-8") == "ok"
        probe.unlink(missing_ok=True)
    except OSError:
        writable = False
    with connect() as conn:
        books_count = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        submissions_count = conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
    stat = DB_PATH.stat() if DB_PATH.exists() else None
    return {
        "data_dir": str(DATA_DIR),
        "upload_dir": str(UPLOAD_DIR),
        "database_path": str(DB_PATH),
        "database_exists": DB_PATH.exists(),
        "database_size": stat.st_size if stat else 0,
        "database_mtime": int(stat.st_mtime) if stat else None,
        "data_dir_writable": writable,
        "books_count": books_count,
        "submissions_count": submissions_count,
        "cwd": os.getcwd(),
    }


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                config_json TEXT NOT NULL,
                comments_enabled INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        migrate_books(conn)
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


def migrate_books(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(books)").fetchall()}
    if "comments_enabled" not in columns:
        conn.execute("ALTER TABLE books ADD COLUMN comments_enabled INTEGER NOT NULL DEFAULT 1")


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
            INSERT INTO books (slug, title, config_json, comments_enabled, created_at, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
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


def book_controls() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT id, slug, title, comments_enabled
            FROM books
            ORDER BY title
            """
        ).fetchall()


def comments_enabled(book: Book) -> bool:
    with connect() as conn:
        row = conn.execute("SELECT comments_enabled FROM books WHERE slug = ?", (book.slug,)).fetchone()
    return bool(row["comments_enabled"]) if row else True


def set_comments_enabled(slug: str, enabled: bool) -> bool:
    with connect() as conn:
        cursor = conn.execute(
            "UPDATE books SET comments_enabled = ?, updated_at = ? WHERE slug = ?",
            (1 if enabled else 0, now(), slug),
        )
    return cursor.rowcount > 0


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


def submission_with_book(submission_id: int) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            """
            SELECT s.*, b.slug AS book_slug, b.title AS book_title
            FROM submissions s
            JOIN books b ON b.id = s.book_id
            WHERE s.id = ?
            """,
            (submission_id,),
        ).fetchone()


def moderate_submission(submission_id: int, action: str) -> sqlite3.Row | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,)).fetchone()
        if not row:
            return None
        if action == "delete":
            conn.execute("DELETE FROM submissions WHERE id = ?", (submission_id,))
            delete_media_files(row)
        elif action in {"approve", "hide", "pending"}:
            status = {"approve": "approved", "hide": "hidden", "pending": "pending"}[action]
            conn.execute("UPDATE submissions SET status = ?, updated_at = ? WHERE id = ?", (status, now(), submission_id))
        else:
            raise ValueError("Acao nao encontrada.")
    return row


def delete_media_files(row: sqlite3.Row) -> None:
    for column in ("media_path", "image_path"):
        if row[column]:
            path = (UPLOAD_DIR / row[column]).resolve()
            if str(path).startswith(str(UPLOAD_DIR.resolve())):
                Path(path).unlink(missing_ok=True)
