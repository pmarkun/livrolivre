from __future__ import annotations

import posixpath
import urllib.parse
from dataclasses import dataclass


@dataclass
class UploadedFile:
    filename: str
    content_type: str
    data: bytes


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
        attrs = disposition_attrs(headers.get("content-disposition", ""))
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


def disposition_attrs(disposition: str) -> dict[str, str]:
    attrs = {}
    for item in disposition.split(";"):
        item = item.strip()
        if "=" in item:
            key, value = item.split("=", 1)
            attrs[key.strip()] = value.strip().strip('"')
    return attrs
