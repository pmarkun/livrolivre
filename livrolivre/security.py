from __future__ import annotations

import hashlib
import hmac
import time
from http.cookies import SimpleCookie

from .settings import APP_SECRET, SESSION_COOKIE


def parse_cookies(header: str | None) -> dict[str, str]:
    jar = SimpleCookie()
    if header:
        jar.load(header)
    return {key: morsel.value for key, morsel in jar.items()}


def sign_session(value: str) -> str:
    sig = hmac.new(APP_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()
    return f"{value}.{sig}"


def valid_session(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    value, sig = token.rsplit(".", 1)
    expected = hmac.new(APP_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected) and value == "admin"


def is_admin(cookie_header: str | None) -> bool:
    cookies = parse_cookies(cookie_header)
    return valid_session(cookies.get(SESSION_COOKIE))


def ip_fingerprint(ip: str) -> str:
    return hashlib.sha256(f"{APP_SECRET}:{ip}".encode()).hexdigest()[:16]


def form_token(book_slug: str, timestamp: int | None = None) -> str:
    timestamp = timestamp or int(time.time())
    value = f"{book_slug}:{timestamp}"
    sig = hmac.new(APP_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()
    return f"{timestamp}.{sig}"


def valid_form_token(book_slug: str, token: str, min_age: int = 2, max_age: int = 60 * 60 * 24) -> bool:
    if not token or "." not in token:
        return False
    raw_ts, sig = token.rsplit(".", 1)
    try:
        timestamp = int(raw_ts)
    except ValueError:
        return False
    value = f"{book_slug}:{timestamp}"
    expected = hmac.new(APP_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    age = int(time.time()) - timestamp
    return min_age <= age <= max_age
