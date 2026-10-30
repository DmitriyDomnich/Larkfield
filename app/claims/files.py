"""Which files a claim accepts, and how their content is recognised."""

import re
from typing import Literal
from urllib.parse import quote

ContentType = Literal["image/jpeg", "image/png", "application/pdf"]

MAX_FILE_BYTES = 10 * 1024 * 1024 # 10 MB

# Every file of a type starts with the same bytes, e.g. every PDF with `%PDF-`. The declared type
# and the filename come from the client; these are checked against the stored file.
FILE_START_BYTES: dict[str, bytes] = {
    "application/pdf": b"%PDF-",
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG\r\n\x1a\n",
}
BYTES_TO_CHECK = max(len(start) for start in FILE_START_BYTES.values())

LABELS: dict[str, str] = {
    "application/pdf": "PDF",
    "image/jpeg": "JPEG",
    "image/png": "PNG",
}


def content_matches_type(first_bytes: bytes, content_type: str) -> bool:
    return first_bytes.startswith(FILE_START_BYTES[content_type])


def content_disposition(filename: str) -> str:
    fallback = re.sub(r"[^A-Za-z0-9._ -]", "_", filename) or "document"
    return f"inline; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"
