"""Single + bulk downloads: per-tier URL resolvers, background fetch queue."""
import asyncio
import contextlib
import html as html_mod
import re
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field

DL_UA = "Mozilla/5.0 (X11; Linux x86_64) research-hub/0.1"
DEFAULT_CAP = 4 * 1024 * 1024 * 1024
CONCURRENCY = 3

_RESOLVE_CACHE: dict[str, tuple[str, str, str]] = {}


def _ua_headers() -> dict[str, str]:
    return {"User-Agent": DL_UA}


def sanitize_name(name: str) -> str:
    name = html_mod.unescape(name or "").strip() or "download"
    name = re.sub(r"[^\w .()\[\]-]", "_", name)[:100]
    return name or "download"


def _filename_from_headers(headers: httpx.Headers, fallback: str) -> str:
    cd = headers.get("content-disposition", "")
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', cd)
    if m:
        return sanitize_name(unquote(m.group(1)))
    return sanitize_name(fallback)


def _guess_name(url: str, content_type: str) -> str:
    path = unquote(urlparse(url).path)
    base = Path(path).name
    if base and "." in base:
        return sanitize_name(base)
    ext = {
        "application/pdf": ".pdf",
        "application/epub+zip": ".epub",
        "text/html": ".html",
    }.get(content_type.split(";")[0].strip(), "")
    return sanitize_name((base or "download") + ext)


async def resolve_url(client: httpx.AsyncClient, url: str, tier: str) -> tuple[str, str, str]:
    """Return (download_url, suggested_name, note). Empty url means unresolvable."""
    key = f"{tier}|{url}"
    cached = _RESOLVE_CACHE.get(key)
    if cached:
        return cached
    result = await _resolve_uncached(client, url, tier)
    _RESOLVE_CACHE[key] = result
    return result


async def _podcast_episode(client: httpx.AsyncClient, feed_url: str) -> tuple[str, str, str]:
    """Podcast RSS feed → latest episode's direct audio URL."""
    response = await client.get(feed_url, headers=_ua_headers(), timeout=40.0, follow_redirects=True)
    response.raise_for_status()
    m = re.search(r'<enclosure[^>]*url="([^"]+)"', response.text)
    if m:
        return m.group(1), "", "podcast episode"
    return "", "", "no enclosure in podcast feed"


async def _resolve_uncached(client: httpx.AsyncClient, url: str, tier: str) -> tuple[str, str, str]:
    try:
        if tier == "arxiv" and "/abs/" in url:
            return url.replace("/abs/", "/pdf/"), "", "arxiv pdf"
        if tier == "libgen" and "/file.php" in url:
            return url, "", "libgen file link"
        if tier == "libgen" and "/book/index.php" in url:
            md5 = url.rsplit("md5=", 1)[-1]
            return f"https://libgen.li/file.php?md5={md5}", "", "libgen file link"
        if tier == "scihub":
            response = await client.get(url, headers=_ua_headers(), timeout=40.0, follow_redirects=True)
            response.raise_for_status()
            m = re.search(r'class\s*=\s*"download"\s*>\s*<a\s+href\s*=\s*"([^"]+)"', response.text)
            if not m:
                m = re.search(r'<(?:embed|iframe)[^>]+src\s*=\s*"([^"]+\.pdf[^"]*)"', response.text)
            if not m:
                m = re.search(r'href\s*=\s*"([^"]*/downloads/[^"]+)"', response.text)
            if m:
                return urljoin(str(response.url), m.group(1)), "", "scihub pdf"
            return "", "", "no pdf link on scihub page"
        if tier == "annas":
            md5 = url.rstrip("/").rsplit("/", 1)[-1]
            mirror = (url.split("/md5/")[0] if "/md5/" in url else "https://annas-archive.li").rstrip("/")
            key = __import__("os").environ.get("ANNAS_KEY")
            if key:
                response = await client.get(
                    f"{mirror}/dyn/api/fast_download.json",
                    params={"md5": md5, "key": key},
                    timeout=40.0,
                    headers=_ua_headers(),
                )
                if response.status_code == 200:
                    data = response.json()
                    dl = data.get("download_url") or ""
                    if dl:
                        return dl, "", "anna's fast download"
                    return "", "", f"anna's: {data.get('error') or 'no fast download'}"
            return "", "", "anna's download needs ANNAS_KEY (membership)"
        if "/details/" in url and "archive.org" in url:
            ident = url.rstrip("/").rsplit("/", 1)[-1]
            response = await client.get(f"https://archive.org/metadata/{ident}", timeout=40.0)
            response.raise_for_status()
            files = response.json().get("files", [])
            ranked = [
                f for f in files
                if str(f.get("format", "")).lower() in ("text pdf", "pdf", "epub", "text")
                or str(f.get("name", "")).lower().endswith((".pdf", ".epub", ".txt"))
            ]
            if ranked:
                ranked.sort(key=lambda f: int(f.get("size") or 0), reverse=True)
                name = ranked[0].get("name", "")
                return f"https://archive.org/download/{ident}/{name}", sanitize_name(name), "archive.org file"
            return "", "", "no downloadable file in archive.org item"
        if tier == "podcasts" and ".rss" in url:
            return await _podcast_episode(client, url)
        if tier == "ccmixter":
            return url, "", "ccmixter audio (browser UA)"
        if tier == "standardebooks":
            response = await client.get(url, headers=_ua_headers(), timeout=40.0, follow_redirects=True)
            response.raise_for_status()
            m = re.search(r'href="([^"]+\.epub)"', response.text)
            if m:
                return urljoin(str(response.url), m.group(1)), "", "standardebooks epub"
            return "", "", "no epub link found"
    except httpx.HTTPError as err:
        return "", "", f"resolver failed: {err.__class__.__name__}"
    return url, "", ""


class DownloadItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    url: str
    title: str = ""
    tier: str = ""


class DownloadRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[DownloadItem] = Field(min_length=1, max_length=200)
    resolve: bool = True


class DownloadManager:
    def __init__(self, state_dir: Path) -> None:
        self.dir = state_dir / "downloads"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = state_dir / "downloads.json"
        self.jobs: dict[str, dict[str, Any]] = self._load()
        self.sem = asyncio.Semaphore(CONCURRENCY)
        self.tasks: dict[str, asyncio.Task] = {}

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.manifest_path.exists():
            return {}
        import json
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self) -> None:
        import json
        self.manifest_path.write_text(json.dumps(self.jobs, indent=1), encoding="utf-8")

    def _active(self) -> int:
        return sum(1 for job in self.jobs.values() if job["status"] in ("queued", "resolving", "running"))

    def enqueue(self, items: list[dict[str, Any]], resolve: bool = True) -> list[dict[str, Any]]:
        queued = []
        for item in items:
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            existing = next(
                (j for j in self.jobs.values() if j["url"] == url and j["status"] != "error"),
                None,
            )
            if existing:
                queued.append(existing)
                continue
            job = {
                "id": uuid.uuid4().hex[:12],
                "url": url,
                "title": str(item.get("title") or ""),
                "tier": str(item.get("tier") or ""),
                "status": "queued",
                "bytes": 0,
                "total": None,
                "filename": "",
                "note": "",
                "error": "",
                "created": time.time(),
            }
            self.jobs[job["id"]] = job
            self._save()
            task = asyncio.get_running_loop().create_task(self._worker(job, resolve))
            self.tasks[job["id"]] = task
            queued.append(job)
        return queued

    async def _worker(self, job: dict[str, Any], resolve: bool) -> None:
        async with self.sem:
            try:
                async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
                    if resolve:
                        job["status"] = "resolving"
                        self._save()
                        dl_url, suggested, note = await resolve_url(client, job["url"], job["tier"])
                        if not dl_url:
                            job["status"] = "error"
                            job["error"] = note or "no direct file"
                            self._save()
                            return
                        job["url"] = dl_url
                        job["note"] = note
                        if suggested:
                            job["filename"] = suggested

                    await self._fetch(client, job)
            except Exception as err:  # noqa: BLE001
                job["status"] = "error"
                job["error"] = f"{err.__class__.__name__}: {err}"[:200]
                self._save()
            finally:
                self.tasks.pop(job["id"], None)

    async def _fetch(self, client: httpx.AsyncClient, job: dict[str, Any]) -> None:
        import os
        cap = int(os.environ.get("HUB_DL_CAP", DEFAULT_CAP))
        job["status"] = "running"
        self._save()
        request = client.build_request("GET", job["url"], headers=_ua_headers())
        response = await client.send(request, stream=True)
        response.raise_for_status()
        total = response.headers.get("content-length")
        job["total"] = int(total) if total and total.isdigit() else None
        ctype = response.headers.get("content-type", "")
        name = job["filename"] or _guess_name(job["url"], ctype)
        path = self.dir / f"{job['id']}_{name}"
        with contextlib.closing(path.open("wb")) as fh:
            received = 0
            async for chunk in response.aiter_bytes(1 << 16):
                received += len(chunk)
                if received > cap:
                    await response.aclose()
                    raise RuntimeError(f"exceeds size cap {cap // (1 << 30)} GiB")
                fh.write(chunk)
                job["bytes"] = received
        job["filename"] = _filename_from_headers(response.headers, name)
        final = self.dir / f"{job['id']}_{job['filename']}"
        if final != path:
            path.rename(final)
            path = final
        job["path"] = str(final)
        job["bytes"] = final.stat().st_size
        job["status"] = "done"
        self._save()

    async def shutdown(self) -> None:
        for task in list(self.tasks.values()):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        self.tasks.clear()

    def list(self) -> list[dict[str, Any]]:
        out = []
        for job in sorted(self.jobs.values(), key=lambda j: -j["created"]):
            out.append({k: v for k, v in job.items() if k != "path"})
        return out

    def remove(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job:
            return False
        task = self.tasks.get(job_id)
        if task:
            task.cancel()
            self.tasks.pop(job_id, None)
        path = job.get("path")
        if path:
            with contextlib.suppress(OSError):
                Path(path).unlink()
        self.jobs.pop(job_id, None)
        self._save()
        return True

    def find(self, job_id: str) -> dict[str, Any] | None:
        job = self.jobs.get(job_id)
        if not job or job.get("status") != "done":
            return None
        return job