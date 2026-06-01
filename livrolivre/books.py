from __future__ import annotations

import json
from dataclasses import dataclass

from .settings import BOOKS_DIR, DEFAULT_BOOK_SLUG


@dataclass(frozen=True)
class Book:
    slug: str
    title: str
    short_title: str
    badge: str
    hero_image: str
    cover_image: str
    theme: dict[str, str]
    copy: dict[str, str]
    subdomains: tuple[str, ...]


BOOKS: dict[str, Book] = {}
SUBDOMAIN_BOOKS: dict[str, str] = {}


def load_books() -> None:
    BOOKS.clear()
    SUBDOMAIN_BOOKS.clear()
    for path in sorted(BOOKS_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        book = Book(
            slug=raw["slug"],
            title=raw["title"],
            short_title=raw.get("short_title", raw["title"]),
            badge=raw.get("badge", raw.get("short_title", raw["title"])),
            hero_image=raw.get("hero_image", ""),
            cover_image=raw.get("cover_image") or raw.get("hero_image", ""),
            theme=raw.get("theme", {}),
            copy=raw.get("copy", {}),
            subdomains=tuple(raw.get("subdomains", [])),
        )
        BOOKS[book.slug] = book
        for subdomain in book.subdomains:
            SUBDOMAIN_BOOKS[subdomain.lower()] = book.slug
    if DEFAULT_BOOK_SLUG not in BOOKS:
        raise RuntimeError(f"DEFAULT_BOOK_SLUG '{DEFAULT_BOOK_SLUG}' nao existe em books/")


def by_request_host_path(host_header: str, path: str) -> tuple[Book, str]:
    host = host_header.split(":", 1)[0].lower()
    subdomain = host.split(".", 1)[0] if "." in host else ""
    if subdomain in SUBDOMAIN_BOOKS:
        return BOOKS[SUBDOMAIN_BOOKS[subdomain]], path
    parts = [part for part in path.split("/") if part]
    if parts and parts[0] in BOOKS:
        remainder = "/" + "/".join(parts[1:])
        return BOOKS[parts[0]], remainder if remainder != "/" else "/"
    return BOOKS[DEFAULT_BOOK_SLUG], path


def url(book: Book, suffix: str = "") -> str:
    suffix = suffix if suffix.startswith("/") or not suffix else f"/{suffix}"
    return f"/{book.slug}{suffix}"
