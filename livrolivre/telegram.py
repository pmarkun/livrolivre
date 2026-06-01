from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from sqlite3 import Row

from .books import Book, url as book_url
from .database import moderate_submission, submission_with_book
from .settings import PUBLIC_BASE_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_TIMEOUT_SECONDS


ACTION_LABELS = {
    "approve": "Aprovado",
    "hide": "Escondido",
    "pending": "Pendente",
    "delete": "Apagado",
}


def enabled() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def notify_submission(submission_id: int, book: Book) -> None:
    if not enabled():
        return
    row = submission_with_book(submission_id)
    if not row:
        return
    text = submission_text(row, book)
    api("sendMessage", {"chat_id": TELEGRAM_CHAT_ID, "text": text, "reply_markup": keyboard(submission_id)})


def send_test_message() -> dict:
    if not enabled():
        return {"ok": False, "error": "telegram_not_configured"}
    return api(
        "sendMessage",
        {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": "Teste do Livro Livre: se esta mensagem chegou, o bot consegue enviar. Os botoes deste teste nao alteram recados reais.",
            "reply_markup": keyboard(0),
        },
    )


def handle_update(update: dict) -> dict:
    callback = update.get("callback_query")
    if not callback:
        return {"ok": True}
    message = callback.get("message") or {}
    chat = message.get("chat") or {}
    print(f"Telegram callback recebido: data={callback.get('data')} chat={chat.get('id')} username={chat.get('username')}")
    if not authorized_chat(chat):
        answer_callback(callback.get("id"), "Este chat nao esta autorizado.")
        print(f"Telegram callback rejeitado: chat nao autorizado. esperado={TELEGRAM_CHAT_ID!r} recebido={chat}")
        return {"ok": False, "error": "unauthorized_chat"}
    action, submission_id = parse_callback_data(callback.get("data", ""))
    if not action:
        answer_callback(callback.get("id"), "Acao desconhecida.")
        return {"ok": False, "error": "bad_callback"}
    try:
        row = moderate_submission(submission_id, action)
    except ValueError:
        answer_callback(callback.get("id"), "Acao desconhecida.")
        return {"ok": False, "error": "bad_action"}
    if not row:
        answer_callback(callback.get("id"), "Recado nao encontrado.")
        return {"ok": False, "error": "missing_submission"}
    label = ACTION_LABELS[action]
    answer_callback(callback.get("id"), label)
    edit_markup(message, f"{message.get('text', '')}\n\nStatus: {label}")
    print(f"Telegram callback aplicado: submission={submission_id} action={action}")
    return {"ok": True, "action": action, "submission_id": submission_id}


def authorized_chat(chat: dict) -> bool:
    configured = str(TELEGRAM_CHAT_ID or "").strip()
    if not configured:
        return False
    chat_id = str(chat.get("id", "")).strip()
    username = str(chat.get("username", "")).strip().lower()
    if configured.startswith("@"):
        return username == configured[1:].lower()
    return chat_id == configured


def submission_text(row: Row, book: Book) -> str:
    visibility = "pode publicar" if row["visibility"] == "public" else "so para autores"
    media = row["media_type"] or "sem midia"
    parts = [
        f"Novo recado: {book.short_title}",
        f"De: {row['author_name'] or 'Leitor misterioso'}",
        f"Local: {row['city'] or 'nao informado'}",
        f"Destino: {visibility}",
        f"Midia: {media}",
    ]
    if row["message"]:
        parts.append("")
        parts.append(row["message"])
    links = submission_links(row, book)
    if links:
        parts.append("")
        parts.extend(links)
    return "\n".join(parts)


def submission_links(row: Row, book: Book) -> list[str]:
    if not PUBLIC_BASE_URL:
        return []
    links = [f"Admin: {PUBLIC_BASE_URL}/admin", f"Pagina: {PUBLIC_BASE_URL}{book_url(book)}"]
    media_path = row["media_path"] or row["image_path"]
    if media_path:
        links.append(f"Midia: {PUBLIC_BASE_URL}/uploads/{media_path}")
    return links


def keyboard(submission_id: int) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "Aprovar", "callback_data": f"ll:approve:{submission_id}"},
                {"text": "Esconder", "callback_data": f"ll:hide:{submission_id}"},
            ],
            [
                {"text": "Pendente", "callback_data": f"ll:pending:{submission_id}"},
                {"text": "Apagar", "callback_data": f"ll:delete:{submission_id}"},
            ],
        ]
    }


def parse_callback_data(data: str) -> tuple[str | None, int]:
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "ll":
        return None, 0
    action = parts[1]
    if action not in ACTION_LABELS:
        return None, 0
    try:
        return action, int(parts[2])
    except ValueError:
        return None, 0


def answer_callback(callback_id: str | None, text: str) -> None:
    if callback_id:
        api("answerCallbackQuery", {"callback_query_id": callback_id, "text": text, "show_alert": False})


def edit_markup(message: dict, text: str) -> None:
    chat = message.get("chat") or {}
    message_id = message.get("message_id")
    chat_id = chat.get("id")
    if chat_id and message_id:
        api("editMessageText", {"chat_id": chat_id, "message_id": message_id, "text": text})


def api(method: str, payload: dict) -> dict:
    if not TELEGRAM_BOT_TOKEN:
        return {"ok": False, "error": "missing_token"}
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TELEGRAM_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Telegram {method} falhou: {exc}; payload={safe_payload(payload)}")
        return {"ok": False, "error": str(exc)}


def safe_payload(payload: dict) -> dict:
    clean = dict(payload)
    if "text" in clean and isinstance(clean["text"], str) and len(clean["text"]) > 160:
        clean["text"] = clean["text"][:160] + "..."
    return clean
