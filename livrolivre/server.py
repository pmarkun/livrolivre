from __future__ import annotations

import hmac
import mimetypes
import shutil
import sqlite3
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .books import BOOKS, Book, by_request_host_path, load_books, url as book_url
from .database import book_id, connect, init_db, now
from .forms import parse_multipart, parse_urlencoded
from .media import save_media
from .security import ip_fingerprint, is_admin, sign_session
from .settings import ADMIN_PASSWORD, DEFAULT_BOOK_SLUG, MAX_UPLOAD_BYTES, ROOT, SESSION_COOKIE, UPLOAD_DIR
from .views import admin_dashboard, admin_login, error_page, public_home


class App(BaseHTTPRequestHandler):
    server_version = "LivroLivre/3.0"

    def do_GET(self) -> None:
        try:
            self.route_get()
        except Exception as exc:
            self.error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self) -> None:
        try:
            self.route_post()
        except ValueError as exc:
            self.error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            self.error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def route_get(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        book, local_path = by_request_host_path(self.headers.get("Host", ""), path)
        if path == "/":
            return self.redirect(book_url(book))
        if local_path == "/":
            params = urllib.parse.parse_qs(parsed.query)
            msg = book.copy["sent_message"] if params.get("sent") else ""
            return self.html(public_home(book, msg))
        if path == "/admin":
            if is_admin(self.headers.get("Cookie")):
                return self.html(admin_dashboard())
            return self.html(admin_login())
        if path.startswith("/static/"):
            return self.file(ROOT / path.lstrip("/"))
        if path.startswith("/uploads/"):
            return self.file(UPLOAD_DIR / path.removeprefix("/uploads/"), cache=False)
        self.error(HTTPStatus.NOT_FOUND, "Pagina nao encontrada.")

    def route_post(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        book, local_path = by_request_host_path(self.headers.get("Host", ""), path)
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_UPLOAD_BYTES + 64_000:
            raise ValueError("O recado ficou grande demais. Tente um arquivo menor.")
        body = self.rfile.read(length)
        if local_path == "/share":
            return self.share(book, body)
        if path == "/admin/login":
            return self.login(body)
        if path == "/admin/logout":
            return self.logout()
        if path.startswith("/admin/submission/"):
            if not is_admin(self.headers.get("Cookie")):
                return self.html(admin_login(), HTTPStatus.UNAUTHORIZED)
            return self.moderate(path)
        self.error(HTTPStatus.NOT_FOUND, "Pagina nao encontrada.")

    def login(self, body: bytes) -> None:
        fields = parse_urlencoded(body)
        if hmac.compare_digest(fields.get("password", ""), ADMIN_PASSWORD):
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/admin")
            self.send_header("Set-Cookie", f"{SESSION_COOKIE}={sign_session('admin')}; HttpOnly; SameSite=Lax; Path=/")
            self.end_headers()
            return
        self.html(admin_login("Senha incorreta."), HTTPStatus.UNAUTHORIZED)

    def logout(self) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/admin")
        self.send_header("Set-Cookie", f"{SESSION_COOKIE}=; Max-Age=0; Path=/")
        self.end_headers()

    def share(self, book: Book, body: bytes) -> None:
        fields, files = parse_multipart(self.headers.get("Content-Type", ""), body)
        if fields.get("consent") != "yes":
            raise ValueError("Confirme que voce tem autorizacao de um adulto.")
        message = fields.get("message", "").strip()
        upload = first_upload(files, ("media_photo", "media_audio", "media_video"))
        if not message and not (upload and upload.data):
            raise ValueError("Envie um texto, uma foto, um audio ou um video.")
        media_type, media_path, original_name = save_media(book, upload)
        visibility = fields.get("visibility", "public")
        if visibility not in {"public", "private"}:
            visibility = "public"
        timestamp = now()
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO submissions (
                    book_id, author_name, city, message, visibility, status, media_type,
                    media_path, media_original_name, created_at, updated_at, user_agent, ip_hash
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    book_id(conn, book.slug),
                    fields.get("author_name", "").strip()[:80],
                    fields.get("city", "").strip()[:80],
                    message[:900],
                    visibility,
                    media_type,
                    media_path,
                    original_name,
                    timestamp,
                    timestamp,
                    self.headers.get("User-Agent", "")[:240],
                    ip_fingerprint(self.client_address[0]),
                ),
            )
        self.redirect(f"{book_url(book)}?sent=1")

    def moderate(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) != 4:
            return self.error(HTTPStatus.NOT_FOUND, "Acao nao encontrada.")
        submission_id = int(parts[2])
        action = parts[3]
        with connect() as conn:
            row = conn.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,)).fetchone()
            if not row:
                return self.error(HTTPStatus.NOT_FOUND, "Recado nao encontrado.")
            if action == "delete":
                conn.execute("DELETE FROM submissions WHERE id = ?", (submission_id,))
                delete_media(row)
            elif action in {"approve", "hide", "pending"}:
                status = {"approve": "approved", "hide": "hidden", "pending": "pending"}[action]
                conn.execute("UPDATE submissions SET status = ?, updated_at = ? WHERE id = ?", (status, now(), submission_id))
            else:
                return self.error(HTTPStatus.NOT_FOUND, "Acao nao encontrada.")
        self.redirect("/admin")

    def file(self, path: Path, cache: bool = True) -> None:
        path = path.resolve()
        allowed_roots = [ROOT / "static", UPLOAD_DIR]
        if not any(str(path).startswith(str(root.resolve())) for root in allowed_roots) or not path.is_file():
            return self.error(HTTPStatus.NOT_FOUND, "Arquivo nao encontrado.")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        if cache:
            self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        with path.open("rb") as fh:
            shutil.copyfileobj(fh, self.wfile)

    def html(self, body: bytes, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def error(self, status: HTTPStatus, message: str) -> None:
        self.html(error_page(message, BOOKS.get(DEFAULT_BOOK_SLUG)), status)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def first_upload(files: dict, names: tuple[str, ...]):
    for name in names:
        upload = files.get(name)
        if upload and upload.filename and upload.data:
            return upload
    return None


def delete_media(row: sqlite3.Row) -> None:
    for column in ("media_path", "image_path"):
        if row[column]:
            (UPLOAD_DIR / row[column]).unlink(missing_ok=True)


def run() -> None:
    load_books()
    init_db()
    import os

    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), App)
    print(f"Livro Livre ouvindo em http://0.0.0.0:{port}")
    server.serve_forever()
