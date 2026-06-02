from __future__ import annotations

import hashlib
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path

from .books import Book
from .forms import UploadedFile
from .settings import ALLOWED_MEDIA_TYPES, MAX_UPLOAD_BYTES, UPLOAD_DIR, upload_limit_mb


def save_media(book: Book, upload: UploadedFile | None) -> tuple[str | None, str | None, str | None]:
    if not upload or not upload.filename or not upload.data:
        return None, None, None
    kind_ext = ALLOWED_MEDIA_TYPES.get(upload.content_type)
    if not kind_ext:
        raise ValueError("Envie imagem ou audio em um formato comum.")
    media_type, ext = kind_ext
    if len(upload.data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"O arquivo ficou grande demais. O limite atual e {upload_limit_mb()} MB.")
    digest = hashlib.sha256(upload.data + secrets.token_bytes(16)).hexdigest()[:24]
    if media_type == "audio":
        converted = convert_audio(upload.data, ext)
        if converted:
            filename = f"{book.slug}/{digest}.ogg"
            target = UPLOAD_DIR / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(converted)
            return media_type, filename, upload.filename[:160]
    filename = f"{book.slug}/{digest}{ext}"
    target = UPLOAD_DIR / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(upload.data)
    return media_type, filename, upload.filename[:160]


def convert_audio(data: bytes, source_ext: str) -> bytes | None:
    if not shutil.which("ffmpeg"):
        print("Conversao de audio pulada: ffmpeg nao encontrado.")
        return None
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / f"source{source_ext}"
        target = Path(tmp) / "voice.ogg"
        source.write_bytes(data)
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "48000",
            "-c:a",
            "libopus",
            "-b:a",
            "32k",
            "-application",
            "voip",
            str(target),
        ]
        try:
            subprocess.run(command, check=True, timeout=20, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as exc:
            error = exc.stderr.decode("utf-8", "replace") if exc.stderr else str(exc)
            print(f"Conversao de audio falhou: {error[:400]}")
            return None
        except (subprocess.SubprocessError, OSError) as exc:
            print(f"Conversao de audio falhou: {exc}")
            return None
        if not target.exists() or target.stat().st_size == 0:
            print("Conversao de audio falhou: arquivo OGG vazio.")
            return None
        return target.read_bytes()
