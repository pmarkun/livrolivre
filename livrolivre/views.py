from __future__ import annotations

import html
import time
from sqlite3 import Row

from .books import BOOKS, Book, url as book_url
from .database import admin_submissions, book_controls, comments_enabled, public_submissions, storage_status
from .security import form_token
from .settings import DEFAULT_BOOK_SLUG, FORM_MIN_AGE_SECONDS


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
  <link rel="stylesheet" href="/static/styles.css">
  <script src="/static/app.js" defer></script>
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
    notice = f'<div class="notice">{escape(message)}</div>' if message else ""
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
      </div>
    </main>
    """
    return page(f"{book.short_title} - Mural de Recados", content, book)


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

        <div class="type-picker" role="group" aria-label="Tipo de recado">
          <button class="type-button active" type="button" data-kind="text" aria-pressed="true"><span aria-hidden="true">T</span>Texto</button>
          <button class="type-button" type="button" data-kind="photo" aria-pressed="false"><span aria-hidden="true">◐</span>Foto</button>
          <button class="type-button" type="button" data-kind="audio" aria-pressed="false"><span aria-hidden="true">♪</span>Audio</button>
          <button class="type-button" type="button" data-kind="video" aria-pressed="false"><span aria-hidden="true">▣</span>Video</button>
        </div>

        <div class="field-row">
          <label>{escape(copy["name_label"])}
            <input name="author_name" maxlength="80" autocomplete="name" placeholder="{escape(copy["name_placeholder"])}">
          </label>
          <label>{escape(copy["city_label"])}
            <input name="city" maxlength="80" autocomplete="address-level2" placeholder="{escape(copy["city_placeholder"])}">
          </label>
        </div>

        <label class="message-field" data-panel="text">{escape(copy["message_label"])}
          <textarea name="message" maxlength="900" rows="5" placeholder="{escape(copy["message_placeholder"])}"></textarea>
        </label>

        <div class="upload-panel hidden" data-panel="photo">
          <label>{escape(copy["photo_label"])}
            <input type="file" name="media_photo" accept="image/png,image/jpeg,image/webp,image/gif" capture="environment">
          </label>
        </div>

        <div class="upload-panel hidden" data-panel="audio">
          <label>{escape(copy["audio_label"])}
            <input type="file" name="media_audio" accept="audio/*" capture>
          </label>
          <div class="recorder" data-recorder>
            <button type="button" class="ghost-button" data-record-audio>Gravar audio</button>
            <span data-record-status>Se o navegador deixar, o microfone abre por aqui.</span>
          </div>
        </div>

        <div class="upload-panel hidden" data-panel="video">
          <label>{escape(copy["video_label"])}
            <input type="file" name="media_video" accept="video/*" capture="user">
          </label>
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
    return f"""
    <section class="control-panel system-panel" aria-labelledby="system-title">
      <h2 id="system-title">Sistema</h2>
      <dl class="system-list">
        <div><dt>DATA_DIR</dt><dd>{escape(status["data_dir"])}</dd></div>
        <div><dt>DATABASE_PATH</dt><dd>{escape(status["database_path"])}</dd></div>
        <div><dt>Banco</dt><dd>{'existe' if status["database_exists"] else 'nao existe'} / {status["database_size"]} bytes / {db_mtime}</dd></div>
        <div><dt>Gravavel</dt><dd>{'sim' if status["data_dir_writable"] else 'nao'}</dd></div>
        <div><dt>Registros</dt><dd>{status["books_count"]} livros / {status["submissions_count"]} recados</dd></div>
      </dl>
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
