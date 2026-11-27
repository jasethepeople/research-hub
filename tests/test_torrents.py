"""Torrent engine routes and the aria2 RPC client."""
from __future__ import annotations

from typing import Any

import httpx
import pytest

from hub.torrents import RPC_TIMEOUT, TorrentClient, TorrentEngineUnavailable


class StubEngine:
    active_dir = "/tmp/t"

    def __init__(self) -> None:
        self.added: list[str] = []
        self.removed: list[str] = []

    def add(self, uri: str) -> str:
        self.added.append(uri)
        return "gid-1"

    def overview(self) -> dict[str, Any]:
        return {"dir": "/tmp/t", "global": {}, "torrents": [{"gid": "gid-1", "status": "active"}]}

    def detail(self, gid: str) -> dict[str, Any]:
        return {"gid": gid, "status": "complete"}

    def remove(self, gid: str) -> dict[str, Any]:
        self.removed.append(gid)
        return {"removed": gid, "state": "canceled"}


class DeadEngine:
    def add(self, uri: str) -> str:
        raise TorrentEngineUnavailable("aria2 RPC unreachable")

    def overview(self) -> dict[str, Any]:
        raise TorrentEngineUnavailable("aria2 RPC unreachable")

    def detail(self, gid: str) -> dict[str, Any]:
        raise TorrentEngineUnavailable("aria2 RPC unreachable")

    def remove(self, gid: str) -> dict[str, Any]:
        raise TorrentEngineUnavailable("aria2 RPC unreachable")


def test_torrent_add_requires_magnet_or_torrent_uri(make_client) -> None:
    with make_client({}) as client:
        client.app.state.torrents = StubEngine()
        response = client.post("/api/torrent/add", json={"uri": "https://example.com/paper.pdf"})
        assert response.status_code == 422
        assert "magnet" in response.json()["detail"]


def test_torrent_add_returns_gid_and_dir(make_client) -> None:
    with make_client({}) as client:
        engine = StubEngine()
        client.app.state.torrents = engine
        response = client.post("/api/torrent/add", json={"uri": "magnet:?xt=urn:btih:abc123"})
        assert response.status_code == 200
        assert response.json() == {"gid": "gid-1", "dir": engine.active_dir}
        assert engine.added == ["magnet:?xt=urn:btih:abc123"]


def test_torrents_list_surfaces_engine_outage_as_503(make_client) -> None:
    with make_client({}) as client:
        client.app.state.torrents = DeadEngine()
        response = client.get("/api/torrents")
        assert response.status_code == 503
        assert "unreachable" in response.json()["detail"]


def test_torrent_detail_and_remove_pass_gids_through(make_client) -> None:
    with make_client({}) as client:
        engine = StubEngine()
        client.app.state.torrents = engine
        assert client.get("/api/torrent/gid-1").json()["gid"] == "gid-1"
        assert client.delete("/api/torrent/gid-1").json()["removed"] == "gid-1"
        assert engine.removed == ["gid-1"]


def test_download_routes_torrent_uris_to_engine_and_keeps_http_downloads(make_client) -> None:
    with make_client({}) as client:
        engine = StubEngine()
        client.app.state.torrents = engine
        response = client.post(
            "/api/download",
            json={
                "items": [
                    {"url": "magnet:?xt=urn:btih:abc123", "tier": "yts"},
                    {"url": "https://example.com/file.pdf", "tier": "libgen"},
                ]
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["torrents"] == [{"gid": "gid-1", "url": "magnet:?xt=urn:btih:abc123"}]
        assert engine.added == ["magnet:?xt=urn:btih:abc123"]
        assert len(body["queued"]) == 1


def test_download_with_dead_engine_does_not_enqueue_the_plain_item(make_client) -> None:
    with make_client({}) as client:
        client.app.state.torrents = DeadEngine()
        response = client.post(
            "/api/download",
            json={"items": [{"url": "magnet:?xt=urn:btih:abc123", "tier": "yts"}]},
        )
        assert response.status_code == 503


def test_torrent_client_maps_aria2_job_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, list[Any]]] = []

    def fake_post(url: str, json: dict[str, Any], timeout: float) -> httpx.Response:
        calls.append((json["method"], json["params"]))
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": json["id"], "result": {"downloadSpeed": "1024"}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("hub.torrents.httpx.post", fake_post)
    engine = TorrentClient(download_dir="/tmp/t")
    stat = engine._call("aria2.getGlobalStat")
    assert stat == {"downloadSpeed": "1024"}
    assert calls[0][0] == "aria2.getGlobalStat"
    assert calls[0][1] == []


def test_torrent_client_maps_compact_job_record() -> None:
    from hub.torrents import _compact

    job = {
        "gid": "g1",
        "status": "active",
        "totalLength": "1000",
        "completedLength": "250",
        "downloadSpeed": "512",
        "numSeeders": "7",
        "connections": "3",
        "bittorrent": {"info": {"name": "caedmon_librivox"}},
    }
    record = _compact(job)
    assert record["progress"] == 0.25
    assert record["name"] == "caedmon_librivox"
    assert record["num_seeders"] == 7
    assert record["download_speed"] == 512


def test_torrent_client_unreachable_rpc_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def refused(url: str, json: dict[str, Any], timeout: float) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=httpx.Request("POST", url))

    monkeypatch.setattr("hub.torrents.httpx.post", refused)
    engine = TorrentClient()
    with pytest.raises(TorrentEngineUnavailable):
        engine._call("aria2.getGlobalStat")


def test_torrent_client_wraps_rpc_error_payloads(monkeypatch: pytest.MonkeyPatch) -> None:
    def error_response(url: str, json: dict[str, Any], timeout: float) -> httpx.Response:
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": json["id"], "error": {"code": 1, "message": "no such download"}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("hub.torrents.httpx.post", error_response)
    engine = TorrentClient()
    with pytest.raises(TorrentEngineUnavailable, match="no such download"):
        engine._call("aria2.tellStatus", ["missing"])


def test_rpc_timeout_is_short_enough_for_request_paths() -> None:
    assert RPC_TIMEOUT <= 5.0