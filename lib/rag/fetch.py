"""RAG's own document downloader: full-size streaming with a 250 MiB cap.

Deliberately separate from the host /api/fetch endpoint, which caps at 500 KiB
and is for dashboard text previews only.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx

MAX_BYTES = 250 * 1024 * 1024
TIMEOUT_SECONDS = 120.0
_CONTENT_DISPOSITION = re.compile(r'filename\*?=(?:UTF-8\'\')?"?([^\";]+)"?', re.IGNORECASE)


def default_store_dir() -> Path:
    base = os.environ.get("HUB_STATE") or "~/.local/share/intel-hub"
    return Path(base).expanduser() / "rag-store"


def _filename(md5: str, response: httpx.Response, url: str) -> str:
    disposition = response.headers.get("content-disposition", "")
    match = _CONTENT_DISPOSITION.search(disposition)
    if match:
        candidate = match.group(1).strip().replace("/", "_")
        if candidate and not candidate.startswith("."):
            return candidate
    suffix = Path(urlsplit(url).path).suffix or ".bin"
    return f"{md5}{suffix}"


def download_document(
    url: str,
    *,
    md5: str,
    store_dir: Path | None = None,
    client: httpx.Client | None = None,
) -> dict:
    """Stream url into the store; refuses to keep more than MAX_BYTES of any file."""
    store = Path(store_dir) if store_dir else default_store_dir()
    store.mkdir(parents=True, exist_ok=True)
    owned = client is None
    try:
        if owned:
            client = httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True)
        with client.stream("GET", url, headers={"User-Agent": "ResearchHub-rag/0.1"}) as response:
            response.raise_for_status()
            target = store / _filename(md5, response, url)
            written = 0
            truncated = False
            with target.open("wb") as handle:
                for chunk in response.iter_bytes():
                    room = MAX_BYTES - written
                    if room <= 0:
                        truncated = True
                        break
                    handle.write(chunk[:room])
                    written += min(len(chunk), room)
            if truncated:
                target.unlink(missing_ok=True)
                return {"path": "", "bytes": 0, "note": "download exceeded the 250 MiB cap and was discarded"}
        return {"path": str(target), "bytes": written, "note": ""}
    except httpx.HTTPError as error:
        return {"path": "", "bytes": 0, "note": f"{error.__class__.__name__}: {error}"}
    finally:
        if owned and client is not None:
            client.close()
