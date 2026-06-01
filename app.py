from __future__ import annotations

import hashlib
import hmac
import html
import mimetypes
import os
import posixpath
import secrets
import shutil
import sqlite3
import time
import urllib.parse
from dataclasses import dataclass
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = Path(os.environ.get("DATABASE_PATH", DATA_DIR / "detetive_chapeuzinho.sqlite3"))
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(7 * 1024 * 1024)))
SESSION_COOKIE = "dc_admin"
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


@dataclass
class UploadedFile:
    filename: str
    content_type: str
    data: bytes


def env_secret(name: str, fallback: str) -> str:
    value = os.environ.get(name)
    if value:
        return value
    return fallback


APP_SECRET = env_secret("APP_SECRET", "troque-este-segredo-no-railway")
ADMIN_PASSWORD = env_secret("ADMIN_PASSWORD", "chapeuzinho")


def db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                author_name TEXT NOT NULL DEFAULT '',
                city TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL DEFAULT '',
                visibility TEXT NOT NULL CHECK (visibility IN ('public', 'private')),
                status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'hidden')) DEFAULT 'pending',
                image_path TEXT,
                image_original_name TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                user_agent TEXT NOT NULL DEFAULT '',
                ip_hash TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_public ON submissions (visibility, status, created_at)")


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


def escape(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def now() -> int:
    return int(time.time())


def fmt_date(ts: int) -> str:
    return time.strftime("%d/%m/%Y, %H:%M", time.localtime(ts))


def ip_fingerprint(ip: str) -> str:
    return hashlib.sha256(f"{APP_SECRET}:{ip}".encode()).hexdigest()[:16]


def parse_urlencoded(body: bytes) -> dict[str, str]:
    parsed = urllib.parse.parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
    return {k: v[-1] if v else "" for k, v in parsed.items()}


def parse_multipart(content_type: str, body: bytes) -> tuple[dict[str, str], dict[str, UploadedFile]]:
    marker = "boundary="
    if marker not in content_type:
        raise ValueError("Formulario sem boundary multipart.")
    boundary = content_type.split(marker, 1)[1].strip().strip('"')
    delimiter = b"--" + boundary.encode()
    fields: dict[str, str] = {}
    files: dict[str, UploadedFile] = {}

    for part in body.split(delimiter):
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"\r\n"):
            part = part[:-2]
        if not part or part == b"--":
            continue
        if part.endswith(b"--"):
            part = part[:-2]
        header_blob, separator, payload = part.partition(b"\r\n\r\n")
        if not separator:
            continue
        headers = {}
        for raw in header_blob.decode("utf-8", "replace").split("\r\n"):
            if ":" in raw:
                key, value = raw.split(":", 1)
                headers[key.lower().strip()] = value.strip()
        payload = payload[:-2] if payload.endswith(b"\r\n") else payload
        disposition = headers.get("content-disposition", "")
        attrs = {}
        for item in disposition.split(";"):
            item = item.strip()
            if "=" in item:
                key, value = item.split("=", 1)
                attrs[key.strip()] = value.strip().strip('"')
        name = attrs.get("name")
        if not name:
            continue
        filename = attrs.get("filename", "")
        if filename:
            files[name] = UploadedFile(
                filename=posixpath.basename(filename),
                content_type=headers.get("content-type", "application/octet-stream").split(";", 1)[0],
                data=payload,
            )
        else:
            fields[name] = payload.decode("utf-8", "replace").strip()
    return fields, files


def save_image(upload: UploadedFile | None) -> tuple[str | None, str | None]:
    if not upload or not upload.filename or not upload.data:
        return None, None
    ext = ALLOWED_IMAGE_TYPES.get(upload.content_type)
    if not ext:
        raise ValueError("Use uma imagem JPG, PNG, WebP ou GIF.")
    if len(upload.data) > MAX_UPLOAD_BYTES:
        raise ValueError("A imagem passou do limite. Tente uma foto menor.")
    digest = hashlib.sha256(upload.data + secrets.token_bytes(16)).hexdigest()[:24]
    filename = f"{digest}{ext}"
    target = UPLOAD_DIR / filename
    target.write_bytes(upload.data)
    return filename, upload.filename[:160]


def page(title: str, content: str, extra_class: str = "") -> bytes:
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body class="{escape(extra_class)}">
  {content}
</body>
</html>""".encode("utf-8")


def public_home(message: str = "") -> bytes:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM submissions
            WHERE visibility = 'public' AND status = 'approved'
            ORDER BY created_at DESC LIMIT 48
            """
        ).fetchall()

    cards = []
    for row in rows:
        image = f'<img src="/uploads/{escape(row["image_path"])}" alt="Foto enviada por leitor">' if row["image_path"] else ""
        where = f'<span>{escape(row["city"])}</span>' if row["city"] else ""
        text = f'<p>{escape(row["message"])}</p>' if row["message"] else '<p class="muted">Um rastro em imagem, sem palavras desta vez.</p>'
        cards.append(
            f"""
            <article class="reader-card">
              {image}
              <div>
                {text}
                <footer><strong>{escape(row["author_name"] or "Leitor misterioso")}</strong>{where}</footer>
              </div>
            </article>
            """
        )
    gallery = "\n".join(cards) or '<p class="empty">As primeiras pistas ainda estao chegando. Volte logo para ler os rastros deixados por outros leitores.</p>'
    notice = f'<div class="notice">{escape(message)}</div>' if message else ""
    content = f"""
    <main class="shell">
      <section class="hero">
        <div class="badge">Detetive Chapeuzinho</div>
        <h1>O Misterio da Sombra Digital continua com voce.</h1>
        <p>Se este livro chegou as suas maos, uma pequena trilha se abriu. Deixe uma foto, uma frase, uma suspeita ou um segredo de leitura.</p>
      </section>

      {notice}

      <section class="form-panel" aria-labelledby="form-title">
        <h2 id="form-title">Deixe seu rastro</h2>
        <p class="rastro">Ao compartilhar, voce deixa um rastro digital, tal qual a Chapeuzinho. Escolha se ele pode aparecer para outros leitores ou se deve seguir apenas para os autores.</p>
        <form method="post" action="/share" enctype="multipart/form-data">
          <label>Nome ou apelido
            <input name="author_name" maxlength="80" autocomplete="name" placeholder="Pode ser um codinome">
          </label>
          <label>Cidade
            <input name="city" maxlength="80" autocomplete="address-level2" placeholder="De onde vem esta pista?">
          </label>
          <label>Comentario
            <textarea name="message" maxlength="900" rows="5" placeholder="Conte o que voce encontrou nas paginas..."></textarea>
          </label>
          <label>Foto
            <input type="file" name="photo" accept="image/png,image/jpeg,image/webp,image/gif">
          </label>
          <fieldset>
            <legend>Destino do rastro</legend>
            <label class="choice"><input type="radio" name="visibility" value="public" checked> Pode ser publico depois da moderacao</label>
            <label class="choice"><input type="radio" name="visibility" value="private"> Enviar somente para os autores</label>
          </fieldset>
          <label class="choice consent"><input type="checkbox" name="consent" value="yes" required> Tenho autorizacao para enviar este texto ou foto e entendo que rastros publicos podem ser vistos por outras pessoas.</label>
          <button type="submit">Enviar pista</button>
        </form>
      </section>

      <section class="gallery" aria-labelledby="gallery-title">
        <h2 id="gallery-title">Rastros ja revelados</h2>
        <div class="cards">{gallery}</div>
      </section>
    </main>
    """
    return page("Detetive Chapeuzinho - Rastros dos leitores", content)


def admin_login(error: str = "") -> bytes:
    err = f'<div class="notice danger">{escape(error)}</div>' if error else ""
    return page(
        "Moderacao - Detetive Chapeuzinho",
        f"""
        <main class="admin-shell login">
          <section class="form-panel">
            <div class="badge">Moderacao</div>
            <h1>Entrada dos autores</h1>
            {err}
            <form method="post" action="/admin/login">
              <label>Senha
                <input type="password" name="password" autofocus required>
              </label>
              <button type="submit">Entrar</button>
            </form>
          </section>
        </main>
        """,
        "admin",
    )


def admin_dashboard() -> bytes:
    with db() as conn:
        rows = conn.execute("SELECT * FROM submissions ORDER BY created_at DESC LIMIT 300").fetchall()
    items = []
    for row in rows:
        image = f'<a href="/uploads/{escape(row["image_path"])}"><img src="/uploads/{escape(row["image_path"])}" alt=""></a>' if row["image_path"] else ""
        visibility = "publico" if row["visibility"] == "public" else "so autores"
        actions = "".join(
            f"""
            <form method="post" action="/admin/submission/{row['id']}/{action}">
              <button type="submit">{label}</button>
            </form>
            """
            for action, label in (("approve", "Aprovar"), ("hide", "Esconder"), ("pending", "Pendente"), ("delete", "Apagar"))
        )
        items.append(
            f"""
            <article class="mod-card status-{escape(row["status"])}">
              {image}
              <div class="mod-body">
                <header>
                  <strong>{escape(row["author_name"] or "Leitor misterioso")}</strong>
                  <span>{escape(visibility)} / {escape(row["status"])} / {fmt_date(row["created_at"])}</span>
                </header>
                <p>{escape(row["message"] or "Sem comentario.")}</p>
                <small>{escape(row["city"])}</small>
                <div class="actions">{actions}</div>
              </div>
            </article>
            """
        )
    listing = "\n".join(items) or '<p class="empty">Nenhum rastro recebido ainda.</p>'
    return page(
        "Moderacao - Detetive Chapeuzinho",
        f"""
        <main class="admin-shell">
          <nav class="admin-nav">
            <div>
              <div class="badge">Moderacao</div>
              <h1>Rastros recebidos</h1>
            </div>
            <form method="post" action="/admin/logout"><button type="submit">Sair</button></form>
          </nav>
          <section class="mod-list">{listing}</section>
        </main>
        """,
        "admin",
    )


class App(BaseHTTPRequestHandler):
    server_version = "DetetiveChapeuzinho/1.0"

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
        if path == "/":
            params = urllib.parse.parse_qs(parsed.query)
            msg = "Seu rastro chegou. Se for publico, ele aparece depois da moderacao." if params.get("sent") else ""
            return self.html(public_home(msg))
        if path == "/admin":
            if self.is_admin():
                return self.html(admin_dashboard())
            return self.html(admin_login())
        if path.startswith("/static/"):
            return self.file(ROOT / path.lstrip("/"))
        if path.startswith("/uploads/"):
            name = posixpath.basename(path)
            return self.file(UPLOAD_DIR / name, cache=False)
        self.error(HTTPStatus.NOT_FOUND, "Pagina nao encontrada.")

    def route_post(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_UPLOAD_BYTES + 64_000:
            raise ValueError("Envio grande demais. Tente uma foto menor.")
        body = self.rfile.read(length)
        if parsed.path == "/share":
            return self.share(body)
        if parsed.path == "/admin/login":
            fields = parse_urlencoded(body)
            if hmac.compare_digest(fields.get("password", ""), ADMIN_PASSWORD):
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", "/admin")
                self.send_header("Set-Cookie", f"{SESSION_COOKIE}={sign_session('admin')}; HttpOnly; SameSite=Lax; Path=/")
                self.end_headers()
                return
            return self.html(admin_login("Senha incorreta."), HTTPStatus.UNAUTHORIZED)
        if parsed.path == "/admin/logout":
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/admin")
            self.send_header("Set-Cookie", f"{SESSION_COOKIE}=; Max-Age=0; Path=/")
            self.end_headers()
            return
        if parsed.path.startswith("/admin/submission/"):
            if not self.is_admin():
                return self.html(admin_login(), HTTPStatus.UNAUTHORIZED)
            return self.moderate(parsed.path)
        self.error(HTTPStatus.NOT_FOUND, "Pagina nao encontrada.")

    def share(self, body: bytes) -> None:
        content_type = self.headers.get("Content-Type", "")
        fields, files = parse_multipart(content_type, body)
        if fields.get("consent") != "yes":
            raise ValueError("Confirme a autorizacao para deixar seu rastro.")
        message = fields.get("message", "").strip()
        upload = files.get("photo")
        if not message and not (upload and upload.data):
            raise ValueError("Envie um comentario, uma foto ou os dois.")
        visibility = fields.get("visibility", "public")
        if visibility not in {"public", "private"}:
            visibility = "public"
        image_path, original_name = save_image(upload)
        timestamp = now()
        with db() as conn:
            conn.execute(
                """
                INSERT INTO submissions (
                    author_name, city, message, visibility, status, image_path,
                    image_original_name, created_at, updated_at, user_agent, ip_hash
                ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)
                """,
                (
                    fields.get("author_name", "").strip()[:80],
                    fields.get("city", "").strip()[:80],
                    message[:900],
                    visibility,
                    image_path,
                    original_name,
                    timestamp,
                    timestamp,
                    self.headers.get("User-Agent", "")[:240],
                    ip_fingerprint(self.client_address[0]),
                ),
            )
        self.redirect("/?sent=1")

    def moderate(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) != 4:
            return self.error(HTTPStatus.NOT_FOUND, "Acao nao encontrada.")
        submission_id = int(parts[2])
        action = parts[3]
        with db() as conn:
            row = conn.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,)).fetchone()
            if not row:
                return self.error(HTTPStatus.NOT_FOUND, "Rastro nao encontrado.")
            if action == "delete":
                conn.execute("DELETE FROM submissions WHERE id = ?", (submission_id,))
                if row["image_path"]:
                    (UPLOAD_DIR / row["image_path"]).unlink(missing_ok=True)
            elif action in {"approve", "hide", "pending"}:
                status = {"approve": "approved", "hide": "hidden", "pending": "pending"}[action]
                conn.execute("UPDATE submissions SET status = ?, updated_at = ? WHERE id = ?", (status, now(), submission_id))
            else:
                return self.error(HTTPStatus.NOT_FOUND, "Acao nao encontrada.")
        self.redirect("/admin")

    def is_admin(self) -> bool:
        cookies = parse_cookies(self.headers.get("Cookie"))
        return valid_session(cookies.get(SESSION_COOKIE))

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
        body = page("Erro", f'<main class="shell"><div class="notice danger">{escape(message)}</div><p><a href="/">Voltar</a></p></main>')
        self.html(body, status)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def main() -> None:
    init_db()
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), App)
    print(f"Detetive Chapeuzinho ouvindo em http://0.0.0.0:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
