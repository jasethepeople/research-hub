"""aria2 JSON-RPC client: torrent add / status / remove for the hub.

Talks to a local aria2c RPC endpoint (127.0.0.1) started as a supervised
process service. Downloads land in ``settings.torrents_dir``. When the
engine is not running, every call raises :class:`TorrentEngineUnavailable`
and the API routes surface it as HTTP 503 instead of hanging.
"""
from __future__ import annotations

import secrets
import time
from pathlib import Path
from typing import Any

import httpx

RPC_TIMEOUT = 3.0
_LIST_CHUNK = 200
_DETAIL_KEYS = ["gid", "status", "totalLength", "completedLength", "downloadSpeed",
                "numSeeders", "connections", "errorCode", "errorMessage", "bittorrent", "files",
                "followedBy"]


class TorrentEngineUnavailable(RuntimeError):
    """The aria2 RPC endpoint is unreachable."""


class TorrentRPCError(RuntimeError):
    """aria2 answered, but refused the call (bad gid, wrong state, ...)."""


def _frozen_name(job: dict[str, Any]) -> str:
    torrent = job.get("bittorrent") or {}
    name = str(torrent.get("info", {}).get("name") or "")
    if name:
        return name
    for path in job.get("files") or []:
        candidate = str(path.get("path") or "").rsplit("/", 1)[-1]
        if candidate:
            return candidate
    return ""


def _compact(job: dict[str, Any]) -> dict[str, Any]:
    total = float(job.get("totalLength") or 0)
    done = float(job.get("completedLength") or 0)
    record = {
        "gid": str(job.get("gid") or ""),
        "status": str(job.get("status") or ""),
        "name": _frozen_name(job),
        "total_length": int(total),
        "completed_length": int(done),
        "progress": round(done / total, 4) if total > 0 else None,
        "download_speed": int(job.get("downloadSpeed") or 0),
        "num_seeders": int(job["numSeeders"]) if str(job.get("numSeeders") or "").isdigit() else None,
        "connections": int(job["connections"]) if str(job.get("connections") or "").isdigit() else None,
    }
    error_code = str(job.get("errorCode") or "").strip()
    if error_code and error_code != "0":
        record["error"] = f"{error_code}: {job.get('errorMessage') or ''}".strip()
    followed = job.get("followedBy")
    if isinstance(followed, list):
        followed = followed[0] if followed else None
    if followed:
        record["followed_by"] = str(followed)
    return record


DEFAULT_DOWNLOAD_DIR = Path.home() / "Downloads" / "torrents"


class TorrentClient:
    def __init__(
        self,
        rpc_url: str = "http://127.0.0.1:6800/jsonrpc",
        download_dir: Path | str = DEFAULT_DOWNLOAD_DIR,
        secret: str = "",
    ) -> None:
        self.rpc_url = rpc_url
        self.download_dir = str(download_dir)
        self.secret = secret

    def _call(self, method: str, params: list[Any] | None = None) -> Any:
        body_params = list(params or [])
        if self.secret:
            body_params = [f"token:{self.secret}", *body_params]
        payload = {
            "jsonrpc": "2.0",
            "id": secrets.token_hex(4),
            "method": method,
            "params": body_params,
        }
        try:
            response = httpx.post(self.rpc_url, json=payload, timeout=RPC_TIMEOUT)
        except httpx.HTTPError as error:
            raise TorrentEngineUnavailable(f"aria2 RPC unreachable at {self.rpc_url}: {error}") from error
        try:
            body = response.json()
        except ValueError as error:
            raise TorrentEngineUnavailable("aria2 RPC returned a non-JSON response") from error
        if "error" in body:
            raise TorrentRPCError(str(body["error"]))
        return body.get("result")

    def ping(self) -> bool:
        try:
            self._call("aria2.getGlobalStat")
        except Exception:
            return False
        return True

    def add(self, uri: str) -> str:
        uri = uri.strip()
        if not uri:
            raise ValueError("uri must not be empty")
        gid = self._call("aria2.addUri", [[uri]])
        return str(gid)

    @property
    def active_dir(self) -> str:
        """The directory aria2 is actually writing to (its own --dir)."""
        try:
            option = self._call("aria2.getGlobalOption", []) or {}
            return str(option.get("dir") or self.download_dir)
        except TorrentEngineUnavailable:
            return self.download_dir

    def resolve_torrent_gid(self, gid: str, attempts: int = 6, delay: float = 0.4) -> str | None:
        """Follow aria2's followedBy chain from a .torrent/magnet wrapper download
        to the gid of the real torrent payload, if one appears."""
        for _ in range(max(attempts, 1)):
            record = self.detail(gid)
            followed = record.get("followed_by")
            if followed:
                return str(followed)
            if record.get("status") not in {"active", "waiting"}:
                return None
            time.sleep(delay)
        return None

    def overview(self) -> dict[str, Any]:
        stat = self._call("aria2.getGlobalStat") or {}
        buckets = {
            "active": self._call("aria2.tellActive", [_DETAIL_KEYS]) or [],
            "waiting": self._call("aria2.tellWaiting", [0, _LIST_CHUNK, _DETAIL_KEYS]) or [],
            "stopped": self._call("aria2.tellStopped", [0, _LIST_CHUNK, _DETAIL_KEYS]) or [],
        }
        return {
            "dir": self.active_dir,
            "global": {
                "download_speed": int(stat.get("downloadSpeed") or 0),
                "upload_speed": int(stat.get("uploadSpeed") or 0),
                "active": int(stat.get("numActive") or 0),
                "waiting": int(stat.get("numWaiting") or 0),
                "stopped": int(stat.get("numStopped") or 0),
            },
            "torrents": [_compact(job) for jobs in buckets.values() for job in jobs],
        }

    def detail(self, gid: str) -> dict[str, Any]:
        job = self._call("aria2.tellStatus", [gid, _DETAIL_KEYS]) or {}
        record = _compact(job)
        record["files"] = [
            {
                "path": str(path.get("path") or ""),
                "length": int(float(path.get("length") or 0)),
                "completed": int(float(path.get("completedLength") or 0)),
            }
            for path in job.get("files") or []
        ]
        return record

    def remove(self, gid: str, files: bool = False) -> dict[str, Any]:
        record: dict[str, Any] = {}
        try:
            record = self.detail(gid)
        except TorrentRPCError:
            pass
        try:
            self._call("aria2.remove", [gid])
            state = "canceled"
        except TorrentRPCError:
            self._call("aria2.removeDownloadResult", [gid])
            state = "purged"
        deleted: list[str] = []
        if files:
            for entry in record.get("files") or []:
                deleted.extend(self._discard_payload(Path(entry["path"])))
        return {"removed": gid, "state": state, "files_deleted": deleted}

    def _discard_payload(self, path: Path) -> list[str]:
        """Best-effort delete of a payload file and its .aria2 control file.
        Refuses anything outside the download directory."""
        removed: list[str] = []
        try:
            resolved = path.resolve()
            resolved.relative_to(Path(self.download_dir).resolve())
        except ValueError:
            return removed
        for candidate in (resolved, Path(f"{resolved}.aria2")):
            try:
                candidate.unlink()
                removed.append(str(candidate))
            except OSError:
                pass
        return removed