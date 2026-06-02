from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from sqlite3 import Row

from .books import Book, url as book_url
from .database import moderate_submission, submission_with_book
from .settings import PUBLIC_BASE_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_TIMEOUT_SECONDS, TELEGRAM_WEBHOOK_SECRET


ACTION_LABELS = {
    "approve": "Aprovado",
    "hide": "Escondido",
    "pending": "Pendente",
    "delete": "Apagado",
}


def enabled() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def webhook_url() -> str:
    return f"{PUBLIC_BASE_URL}/telegram/webhook" if PUBLIC_BASE_URL else ""


def ensure_webhook() -> dict:
    if not TELEGRAM_BOT_TOKEN or not PUBLIC_BASE_URL:
        return {"ok": False, "error": "missing_token_or_public_base_url"}
    payload = {
        "url": webhook_url(),
        "allowed_updates": ["callback_query"],
    }
    if TELEGRAM_WEBHOOK_SECRET:
        payload["secret_token"] = TELEGRAM_WEBHOOK_SECRET
    result = api("setWebhook", payload)
    print(f"Telegram webhook configurado: url={payload['url']} ok={result.get('ok')} result={result}")
    return result


def webhook_info() -> dict:
    if not TELEGRAM_BOT_TOKEN:
        return {"ok": False, "error": "missing_token"}
    return api("getWebhookInfo", {})


def notify_submission(submission_id: int, book: Book) -> None:
    if not enabled():
        return
    row = submission_with_book(submission_id)
    if not row:
        return
    text = submission_text(row, book, include_media_link=False)
    markup = keyboard(submission_id)
    if not send_media(row, text, markup):
        api("sendMessage", {"chat_id": TELEGRAM_CHAT_ID, "text": text, "reply_markup": markup})


def send_test_message() -> dict:
    if not enabled():
        return {"ok": False, "error": "telegram_not_configured"}
    return api(
        "sendMessage",
        {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": "Teste do Livro Livre: se esta mensagem chegou, o bot consegue enviar. Os botoes deste teste nao alteram recados reais.",
            "reply_markup": test_keyboard(),
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
    if action == "test":
        answer_callback(callback.get("id"), "Callback funcionando")
        edit_markup(message, f"{message.get('text', '')}\n\nStatus: Callback funcionando")
        print("Telegram callback de teste aplicado")
        return {"ok": True, "action": "test"}
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


def submission_text(row: Row, book: Book, include_media_link: bool = True) -> str:
    visibility = "pode publicar" if row["visibility"] == "public" else "so para autores"
    media = row["media_type"] or "sem midia"
    parts = [
        f"Novo recado: {book.short_title}",
        f"De: {row['author_name'] or 'Leitor misterioso'}",
        f"Idade: {row['age'] or 'nao informada'}",
        f"Local: {row['city'] or 'nao informado'}",
        f"Destino: {visibility}",
        f"Midia: {media}",
    ]
    if row["message"]:
        parts.append("")
        parts.append(row["message"])
    links = submission_links(row, book, include_media=include_media_link)
    if links:
        parts.append("")
        parts.extend(links)
    return "\n".join(parts)


def submission_links(row: Row, book: Book, include_media: bool = True) -> list[str]:
    if not PUBLIC_BASE_URL:
        return []
    links = [f"Admin: {PUBLIC_BASE_URL}/admin", f"Pagina: {PUBLIC_BASE_URL}{book_url(book)}"]
    media_path = row["media_path"] or row["image_path"]
    if include_media and media_path:
        links.append(f"Midia: {PUBLIC_BASE_URL}/uploads/{media_path}")
    return links


def media_url(row: Row) -> str:
    media_path = row["media_path"] or row["image_path"]
    if not PUBLIC_BASE_URL or not media_path:
        return ""
    return f"{PUBLIC_BASE_URL}/uploads/{media_path}"


def send_media(row: Row, text: str, reply_markup: dict) -> bool:
    url = media_url(row)
    if not enabled() or not url:
        return False
    media_type = row["media_type"] or ("image" if row["image_path"] else "")
    caption = telegram_caption(text)
    if media_type == "image":
        result = api("sendPhoto", {"chat_id": TELEGRAM_CHAT_ID, "photo": url, "caption": caption, "reply_markup": reply_markup})
        return bool(result.get("ok"))
    elif media_type == "audio":
        if str(row["media_path"] or "").lower().endswith(".ogg"):
            result = api("sendVoice", {"chat_id": TELEGRAM_CHAT_ID, "voice": url, "caption": caption, "reply_markup": reply_markup})
            if result.get("ok"):
                return True
        result = api("sendAudio", {"chat_id": TELEGRAM_CHAT_ID, "audio": url, "caption": caption, "reply_markup": reply_markup})
        if result.get("ok"):
            return True
        result = api("sendDocument", {"chat_id": TELEGRAM_CHAT_ID, "document": url, "caption": caption, "reply_markup": reply_markup})
        return bool(result.get("ok"))
    return False


def telegram_caption(text: str) -> str:
    if len(text) <= 950:
        return text
    return text[:947].rstrip() + "..."


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


def test_keyboard() -> dict:
    return {"inline_keyboard": [[{"text": "Testar callback", "callback_data": "ll:test:0"}]]}


def parse_callback_data(data: str) -> tuple[str | None, int]:
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "ll":
        return None, 0
    action = parts[1]
    if action != "test" and action not in ACTION_LABELS:
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
