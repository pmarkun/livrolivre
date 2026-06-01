from __future__ import annotations

import html
import time
from sqlite3 import Row

from .books import BOOKS, Book, url as book_url
from .database import admin_submissions, book_controls, comments_enabled, public_submissions, storage_status
from .security import form_token
from .settings import ASSET_VERSION, DEFAULT_BOOK_SLUG, FORM_MIN_AGE_SECONDS, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_WEBHOOK_SECRET
from .telegram import webhook_url


def escape(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def fmt_date(ts: int) -> str:
    return time.strftime("%d/%m/%Y, %H:%M", time.localtime(ts))


def theme_style(book: Book) -> str:
    names = {
        "ink": "--ink",
        "muted": "--muted",
        "paper": "--paper",
        "panel": "--panel",
        "line": "--line",
        "red": "--red",
        "red_dark": "--red-dark",
        "forest": "--forest",
        "gold": "--gold",
        "blue": "--blue",
    }
    return "; ".join(f"{css}: {escape(book.theme[key])}" for key, css in names.items() if key in book.theme)


def page(title: str, content: str, book: Book | None = None, extra_class: str = "") -> bytes:
    style = f' style="{theme_style(book)}"' if book else ""
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <link rel="stylesheet" href="/static/styles.css?v={escape(ASSET_VERSION)}">
  <script src="/static/app.js?v={escape(ASSET_VERSION)}" defer></script>
</head>
<body class="{escape(extra_class)}"{style}>
  {content}
</body>
</html>""".encode("utf-8")


def media_html(row: Row) -> str:
    path = row["media_path"] or row["image_path"]
    media_type = row["media_type"] or ("image" if row["image_path"] else "")
    if not path:
        return ""
    src = f"/uploads/{escape(path)}"
    if media_type == "image":
        return f'<img src="{src}" alt="Imagem enviada por leitor">'
    if media_type == "video":
        return f'<video src="{src}" controls playsinline preload="metadata"></video>'
    if media_type == "audio":
        return f'<div class="audio-note"><span aria-hidden="true">♪</span><audio src="{src}" controls preload="metadata"></audio></div>'
    return ""


def public_home(book: Book, message: str = "") -> bytes:
    copy = book.copy
    accepting_comments = comments_enabled(book)
    cards = []
    for row in public_submissions(book):
        where = f'<span>{escape(row["city"])}</span>' if row["city"] else ""
        text = f'<p>{escape(row["message"])}</p>' if row["message"] else '<p class="muted">Um recado sem palavras, mas cheio de pista.</p>'
        cards.append(
            f"""
            <article class="reader-card">
              {media_html(row)}
              <div>
                {text}
                <footer><strong>{escape(row["author_name"] or "Leitor misterioso")}</strong>{where}</footer>
              </div>
            </article>
            """
        )
    gallery = "\n".join(cards) or f'<p class="empty">{escape(copy["empty_gallery"])}</p>'
    notice = sent_notice(book, message)
    hero_image = f'<img src="{escape(book.cover_image)}" alt="" aria-hidden="true">' if book.cover_image else ""
    form = response_form(book, accepting_comments)
    content = f"""
    <main class="book-page">
      <section class="welcome">
        <div class="cover">{hero_image}</div>
        <div class="letter">
          <div class="badge">{escape(book.badge)}</div>
          <h1>{escape(copy["hero_title"])}</h1>
          <p>{escape(copy["hero_intro"])}</p>
          <p>{escape(copy["hero_question"])}</p>
          <p class="adult-note">{escape(copy["adult_note"])}</p>
        </div>
      </section>

      <div class="shell">
        {notice}

        {form}

        <section class="gallery" aria-labelledby="gallery-title">
          <h2 id="gallery-title">{escape(copy["gallery_title"])}</h2>
          <div class="cards">{gallery}</div>
        </section>

        <footer class="site-footer">
          <a href="https://sabichinho.com.br" target="_blank" rel="noopener noreferrer">Sobre</a>
          <p>Esta ferramenta do Sabichinho aproxima livros livres de seus leitores: cada QR Code abre um pequeno mural onde crianças e adultos podem devolver fotos, áudios e impressões para os autores, sempre com moderação.</p>
        </footer>
      </div>
    </main>
    """
    return page(f"{book.short_title} - Mural de Recados", content, book)


def sent_notice(book: Book, message: str) -> str:
    if not message:
        return ""
    title = book.copy.get("sent_title", "Recado enviado") if message == book.copy.get("sent_message") else "Ops, faltou a pista"
    return f"""
    <section class="notice sent-notice" aria-live="polite">
      <strong>{escape(title)}</strong>
      <p>{escape(message)}</p>
    </section>
    """


def response_form(book: Book, accepting_comments: bool) -> str:
    copy = book.copy
    if not accepting_comments:
        return f"""
        <section class="message-board closed-board" aria-labelledby="form-title">
          <h2 id="form-title">{escape(copy["form_title"])}</h2>
          <p class="empty">A caixa de recados esta fechada por enquanto. O mural continua aberto para leitura.</p>
        </section>
        """
    return f"""
    <section class="message-board" aria-labelledby="form-title">
      <h2 id="form-title">{escape(copy["form_title"])}</h2>
      <form method="post" action="{escape(book_url(book, '/share'))}" enctype="multipart/form-data" data-min-age="{FORM_MIN_AGE_SECONDS}">
        <input type="hidden" name="form_token" value="{escape(form_token(book.slug))}">
        <label class="trap-field">Nao preencha este campo
          <input name="website" tabindex="-1" autocomplete="off">
        </label>

        <div class="field-row">
          <label>{escape(copy["name_label"])}
            <input name="author_name" maxlength="80" autocomplete="name" placeholder="{escape(copy["name_placeholder"])}">
          </label>
          <label>{escape(copy["city_label"])}
            <input name="city" maxlength="80" autocomplete="address-level2" placeholder="{escape(copy["city_placeholder"])}">
          </label>
        </div>

        <textarea class="sr-only" name="message" maxlength="900" rows="5" data-message-input>{escape("")}</textarea>
        <input class="sr-only" type="file" name="media_photo" accept="image/png,image/jpeg,image/webp,image/gif" capture="environment" data-photo-input>
        <input class="sr-only" type="file" name="media_audio" accept="audio/*" capture data-audio-input>

        <div class="action-dock" role="group" aria-label="Escolha o tipo de recado">
          <button class="action-button" type="button" data-open-modal="text" aria-label="Escrever texto"><span aria-hidden="true">T</span></button>
          <button class="action-button" type="button" data-open-modal="photo" aria-label="Tirar foto"><span aria-hidden="true">▢</span></button>
          <button class="action-button" type="button" data-open-modal="audio" aria-label="Gravar áudio"><span aria-hidden="true">♪</span></button>
        </div>

        <section class="content-preview empty" data-content-preview aria-live="polite">
          <p>Escolha texto, foto ou áudio para deixar sua pista.</p>
        </section>

        <div class="modal hidden" data-modal="text" role="dialog" aria-modal="true" aria-labelledby="text-modal-title">
          <div class="modal-card">
            <button class="modal-close" type="button" data-close-modal aria-label="Fechar">×</button>
            <h3 id="text-modal-title">Escreva sua pista</h3>
            <textarea maxlength="900" rows="8" placeholder="{escape(copy["message_placeholder"])}" data-text-draft></textarea>
            <button class="send-button compact" type="button" data-save-text>Salvar texto</button>
          </div>
        </div>

        <div class="modal hidden" data-modal="photo" role="dialog" aria-modal="true" aria-labelledby="photo-modal-title">
          <div class="modal-card camera-modal-card" data-camera>
            <button class="modal-close" type="button" data-close-modal aria-label="Fechar">×</button>
            <h3 id="photo-modal-title">Fotografe sua pista</h3>
            <div class="camera-view">
              <video data-camera-preview autoplay playsinline muted></video>
              <img data-photo-preview alt="Prévia da foto capturada">
              <div class="camera-placeholder">
                <span aria-hidden="true">▢</span>
                <p>A câmera aparece aqui.</p>
              </div>
            </div>
            <div class="camera-actions">
              <button type="button" class="shutter-button" data-capture-photo aria-label="Fotografar" disabled></button>
              <button type="button" class="ghost-button" data-open-camera>Abrir câmera</button>
              <button type="button" class="ghost-button hidden" data-retake-photo>Tirar outra</button>
              <button type="button" class="ghost-button" data-pick-photo>Escolher foto</button>
            </div>
            <canvas data-photo-canvas hidden></canvas>
            <p class="camera-status" data-camera-status>Abra a câmera ou escolha uma foto do aparelho.</p>
          </div>
        </div>

        <div class="modal hidden" data-modal="audio" role="dialog" aria-modal="true" aria-labelledby="audio-modal-title">
          <div class="modal-card">
            <button class="modal-close" type="button" data-close-modal aria-label="Fechar">×</button>
            <h3 id="audio-modal-title">Grave seu recado</h3>
            <div class="audio-recorder" data-recorder>
              <div class="wave" data-wave aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>
              <button type="button" class="record-button" data-record-audio aria-label="Gravar áudio"></button>
              <audio class="hidden" data-audio-preview controls></audio>
              <div class="audio-tools">
                <button type="button" class="ghost-button hidden" data-play-audio>Ouvir</button>
                <button type="button" class="ghost-button danger hidden" data-delete-audio>Apagar</button>
                <button type="button" class="ghost-button" data-pick-audio>Escolher arquivo</button>
              </div>
              <span data-record-status>Toque no círculo para gravar.</span>
            </div>
          </div>
        </div>

        <fieldset class="publish-choice">
          <legend>{escape(copy["visibility_legend"])}</legend>
          <label class="choice"><input type="radio" name="visibility" value="public" checked> {escape(copy["public_label"])}</label>
          <label class="choice"><input type="radio" name="visibility" value="private"> {escape(copy["private_label"])}</label>
        </fieldset>

        <label class="choice consent"><input type="checkbox" name="consent" value="yes" required> {escape(copy["consent"])}</label>
        <button class="send-button" type="submit" data-ready-label="{escape(copy["submit_label"])}">{escape(copy["submit_label"])}</button>
      </form>
    </section>
    """


def admin_login(error: str = "") -> bytes:
    err = f'<div class="notice danger">{escape(error)}</div>' if error else ""
    book = BOOKS[DEFAULT_BOOK_SLUG]
    return page(
        "Moderacao - Livro Livre",
        f"""
        <main class="admin-shell login">
          <section class="message-board admin-login">
            <div class="badge">Livro Livre</div>
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
        book,
        "admin",
    )


def admin_dashboard() -> bytes:
    controls = admin_controls()
    system = system_panel()
    items = []
    for row in admin_submissions():
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
              {media_html(row)}
              <div class="mod-body">
                <header>
                  <strong>{escape(row["author_name"] or "Leitor misterioso")}</strong>
                  <span>{escape(row["book_title"])} / {escape(visibility)} / {escape(row["status"])} / {fmt_date(row["created_at"])}</span>
                </header>
                <p>{escape(row["message"] or "Sem texto.")}</p>
                <small>{escape(row["city"])}</small>
                <div class="actions">{actions}</div>
              </div>
            </article>
            """
        )
    listing = "\n".join(items) or '<p class="empty">Nenhum recado recebido ainda.</p>'
    book_links = "".join(f'<a href="{escape(book_url(book))}">{escape(book.short_title)}</a>' for book in BOOKS.values())
    return page(
        "Moderacao - Livro Livre",
        f"""
        <main class="admin-shell">
          <nav class="admin-nav">
            <div>
              <div class="badge">Moderacao</div>
              <h1>Recados recebidos</h1>
              <div class="book-links">{book_links}</div>
            </div>
            <form method="post" action="/admin/logout"><button type="submit">Sair</button></form>
          </nav>
          {system}
          {controls}
          <section class="mod-list">{listing}</section>
        </main>
        """,
        BOOKS[DEFAULT_BOOK_SLUG],
        "admin",
    )


def system_panel() -> str:
    status = storage_status()
    db_mtime = fmt_date(status["database_mtime"]) if status["database_mtime"] else "nunca"
    telegram_ready = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
    return f"""
    <section class="control-panel system-panel" aria-labelledby="system-title">
      <h2 id="system-title">Sistema</h2>
      <dl class="system-list">
        <div><dt>DATA_DIR</dt><dd>{escape(status["data_dir"])}</dd></div>
        <div><dt>DATABASE_PATH</dt><dd>{escape(status["database_path"])}</dd></div>
        <div><dt>Banco</dt><dd>{'existe' if status["database_exists"] else 'nao existe'} / {status["database_size"]} bytes / {db_mtime}</dd></div>
        <div><dt>Gravavel</dt><dd>{'sim' if status["data_dir_writable"] else 'nao'}</dd></div>
        <div><dt>Registros</dt><dd>{status["books_count"]} livros / {status["submissions_count"]} recados</dd></div>
        <div><dt>Telegram</dt><dd>{'configurado' if telegram_ready else 'nao configurado'} / chat {escape(TELEGRAM_CHAT_ID or '-')} / secret {'sim' if TELEGRAM_WEBHOOK_SECRET else 'nao'}</dd></div>
        <div><dt>Webhook esperado</dt><dd>{escape(webhook_url() or '-')}</dd></div>
      </dl>
      <form class="inline-admin-form" method="post" action="/admin/telegram/test">
        <button type="submit">Testar Telegram</button>
      </form>
      <form class="inline-admin-form" method="post" action="/admin/telegram/webhook">
        <button type="submit">Registrar webhook</button>
      </form>
    </section>
    """


def admin_controls() -> str:
    rows = []
    for row in book_controls():
        enabled = bool(row["comments_enabled"])
        action = "close" if enabled else "open"
        label = "Fechar recados" if enabled else "Abrir recados"
        status = "Recebendo recados" if enabled else "Recados fechados"
        rows.append(
            f"""
            <article class="control-card">
              <div>
                <strong>{escape(row["title"])}</strong>
                <span>{status}</span>
              </div>
              <form method="post" action="/admin/book/{escape(row["slug"])}/comments/{action}">
                <button type="submit">{label}</button>
              </form>
            </article>
            """
        )
    return f"""
    <section class="control-panel" aria-labelledby="control-title">
      <h2 id="control-title">Controle dos livros</h2>
      <div class="control-list">{''.join(rows)}</div>
    </section>
    """


def error_page(message: str, book: Book | None) -> bytes:
    return page("Erro", f'<main class="shell"><div class="notice danger">{escape(message)}</div><p><a href="/">Voltar</a></p></main>', book)
