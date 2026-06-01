from __future__ import annotations

import hmac
import json
import mimetypes
import shutil
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .books import BOOKS, Book, by_request_host_path, load_books, url as book_url
from .database import book_id, comments_enabled, connect, init_db, moderate_submission, now, set_comments_enabled, storage_status
from .forms import parse_multipart, parse_urlencoded
from .media import save_media
from .security import ip_fingerprint, is_admin, sign_session, valid_form_token
from .settings import ADMIN_PASSWORD, DEFAULT_BOOK_SLUG, MAX_UPLOAD_BYTES, ROOT, SESSION_COOKIE, TELEGRAM_WEBHOOK_SECRET, UPLOAD_DIR, upload_limit_mb
from .telegram import ensure_webhook, handle_update, notify_submission, send_test_message
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
            if params.get("error") == ["empty"]:
                msg = "Antes de enviar, deixe uma pista: escreva um recado, escolha uma foto, grave um áudio ou mande um vídeo."
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
            raise ValueError(f"O recado ficou grande demais. O limite atual e {upload_limit_mb()} MB.")
        body = self.rfile.read(length)
        if local_path == "/share":
            return self.share(book, body)
        if path == "/telegram/webhook":
            return self.telegram_webhook(body)
        if path == "/admin/login":
            return self.login(body)
        if path == "/admin/logout":
            return self.logout()
        if path == "/admin/telegram/test":
            if not is_admin(self.headers.get("Cookie")):
                return self.html(admin_login(), HTTPStatus.UNAUTHORIZED)
            return self.telegram_test()
        if path == "/admin/telegram/webhook":
            if not is_admin(self.headers.get("Cookie")):
                return self.html(admin_login(), HTTPStatus.UNAUTHORIZED)
            return self.telegram_register_webhook()
        if path.startswith("/admin/book/"):
            if not is_admin(self.headers.get("Cookie")):
                return self.html(admin_login(), HTTPStatus.UNAUTHORIZED)
            return self.book_control(path)
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
        if not comments_enabled(book):
            raise ValueError("A caixa de recados deste livro esta fechada por enquanto.")
        fields, files = parse_multipart(self.headers.get("Content-Type", ""), body)
        if fields.get("website"):
            raise ValueError("Nao foi possivel receber este recado.")
        if not valid_form_token(book.slug, fields.get("form_token", "")):
            raise ValueError("Abra a pagina novamente e tente enviar o recado mais uma vez.")
        if fields.get("consent") != "yes":
            raise ValueError("Confirme que voce tem autorizacao de um adulto.")
        message = fields.get("message", "").strip()
        upload = first_upload(files, ("media_photo", "media_audio", "media_video"))
        if not message and not (upload and upload.data):
            return self.redirect(f"{book_url(book)}?error=empty")
        media_type, media_path, original_name = save_media(book, upload)
        visibility = fields.get("visibility", "public")
        if visibility not in {"public", "private"}:
            visibility = "public"
        timestamp = now()
        with connect() as conn:
            cursor = conn.execute(
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
            submission_id = int(cursor.lastrowid)
        notify_submission(submission_id, book)
        self.redirect(f"{book_url(book)}?sent=1")

    def moderate(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) != 4:
            return self.error(HTTPStatus.NOT_FOUND, "Acao nao encontrada.")
        submission_id = int(parts[2])
        action = parts[3]
        try:
            row = moderate_submission(submission_id, action)
        except ValueError:
            return self.error(HTTPStatus.NOT_FOUND, "Acao nao encontrada.")
        if not row:
            return self.error(HTTPStatus.NOT_FOUND, "Recado nao encontrado.")
        self.redirect("/admin")

    def book_control(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) != 5 or parts[0] != "admin" or parts[1] != "book" or parts[3] != "comments":
            return self.error(HTTPStatus.NOT_FOUND, "Acao nao encontrada.")
        slug = parts[2]
        action = parts[4]
        if action not in {"open", "close"}:
            return self.error(HTTPStatus.NOT_FOUND, "Acao nao encontrada.")
        if not set_comments_enabled(slug, action == "open"):
            return self.error(HTTPStatus.NOT_FOUND, "Livro nao encontrado.")
        self.redirect("/admin")

    def telegram_webhook(self, body: bytes) -> None:
        if TELEGRAM_WEBHOOK_SECRET:
            header = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if header != TELEGRAM_WEBHOOK_SECRET:
                return self.json({"ok": False, "error": "bad_secret"}, HTTPStatus.UNAUTHORIZED)
        update = json.loads(body.decode("utf-8"))
        result = handle_update(update)
        self.json(result)

    def telegram_test(self) -> None:
        result = send_test_message()
        if result.get("ok"):
            return self.redirect("/admin?telegram=test-ok")
        return self.redirect("/admin?telegram=test-failed")

    def telegram_register_webhook(self) -> None:
        result = ensure_webhook()
        if result.get("ok"):
            return self.redirect("/admin?telegram=webhook-ok")
        return self.redirect("/admin?telegram=webhook-failed")

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

    def json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
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


def run() -> None:
    load_books()
    init_db()
    import os

    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), App)
    print(f"Livro Livre ouvindo em http://0.0.0.0:{port}")
    status = storage_status()
    print(f"DATA_DIR={status['data_dir']}")
    print(f"DATABASE_PATH={status['database_path']} exists={status['database_exists']} size={status['database_size']}")
    ensure_webhook()
    server.serve_forever()
