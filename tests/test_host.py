import asyncio
import socket
from datetime import UTC, datetime, timedelta

import mcp
import pytest

from hub.cache import ResponseCache
from hub.fetch import MAX_BYTES, FetchError, fetch_url
from hub.registry import assert_mcp_v1, tier_environment
from hub.storage import Store
from tests.conftest import stub_config


def test_dashboard_has_three_panes_and_optional_fourth(make_client):
    with make_client({}) as client:
        page = client.get("/").text
        assert page.count('<section class="pane"') == 3
        assert "const fourthPaneEnabled = false" in page
    with make_client({}, fourth_pane=True) as client:
        page = client.get("/").text
        assert page.count('<section class="pane"') == 3
        assert "const fourthPaneEnabled = true" in page


def test_drop_in_tier_appears_without_host_changes(make_client):
    with make_client(stub_config("literature")) as client:
        response = client.get("/api/search", params={"query": "test query"})
        assert response.status_code == 200
        body = response.json()
        assert body["results"][0]["title"] == "Example Research Result"
        assert body["results"][0]["tier"] == "literature"
        assert body["notes"]["literature"]["state"] == "ok"
        assert client.get("/api/health").json()["tiers"]["literature"]["state"] == "ok"


def test_bad_tiers_do_not_fail_or_block_good_tier(make_client):
    config = {
        **stub_config("good"),
        **stub_config("raises", "raise"),
        **stub_config("sleeps", "sleep"),
        **stub_config("exits", "exit"),
    }
    with make_client(config, timeout=0.2) as client:
        response = client.get("/api/search", params={"query": "parallel"})
        assert response.status_code == 200
        body = response.json()
        assert body["results"][0]["tier"] == "good"
        for name in ("raises", "exits"):
            assert body["notes"][name]["state"] == "degraded"
            assert body["notes"][name]["note"]
        # A timeout is transient: the tier keeps its prior state, but the
        # note records the timeout.
        assert body["notes"]["sleeps"]["state"] == "ok"
        assert "TimeoutError" in body["notes"]["sleeps"]["note"]


def test_dedupe_keeps_first_registry_tier_and_records_other(make_client):
    config = {**stub_config("literature"), **stub_config("vulns")}
    with make_client(config) as client:
        body = client.get("/api/search", params={"query": "dedupe"}).json()
        assert len(body["results"]) == 1
        assert body["results"][0]["tier"] == "literature"
        assert body["results"][0]["also_on"] == ["vulns"]


def test_health_always_lists_every_registered_tier(make_client):
    config = {**stub_config("first"), **stub_config("second")}
    with make_client(config) as client:
        health = client.get("/api/health").json()
        assert set(health["tiers"]) == {"first", "second"}
        assert health["cache_ttl"] == 900


def test_health_mirrors_every_tier_at_top_level_and_keeps_nested_shape(make_client):
    with make_client(stub_config("literature")) as client:
        health = client.get("/api/health").json()
        assert health["tiers"]["literature"] == health["literature"]
        assert health["literature"]["state"] == "ok"
        assert health["cache_ttl"] == 900




def test_cache_lru_evicts_at_500_entries():
    cache = ResponseCache(ttl=900, maxsize=500)
    for index in range(500):
        cache.put(("tier", str(index)), {"value": index})
    assert cache.get(("tier", "0")) == {"value": 0}
    cache.put(("tier", "500"), {"value": 500})
    assert len(cache) == 500
    assert cache.get(("tier", "1")) is None
    assert cache.get(("tier", "0")) == {"value": 0}


def test_pin_sweeper_removes_expired_pins(tmp_path):
    store = Store(tmp_path)
    store.initialize()
    expired = store.pin({"title": "old"}, datetime.now(UTC) - timedelta(seconds=10))
    permanent = store.pin({"title": "keep"})
    assert len(store.list_pins()) == 1
    assert store.sweep_expired() == 1
    assert [pin["id"] for pin in store.list_pins()] == [permanent["id"]]
    assert expired["id"] != permanent["id"]


def test_pin_cap_is_500(tmp_path):
    store = Store(tmp_path)
    store.initialize()
    for index in range(500):
        store.pin({"title": str(index)})
    with pytest.raises(OverflowError, match="500"):
        store.pin({"title": "overflow"})


def test_version_guard_exits_2_for_mcp_v2(monkeypatch, capsys):
    monkeypatch.setattr(mcp, "__version__", "2.0.0", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        assert_mcp_v1()
    assert exit_info.value.code == 2
    assert "requires mcp 1.x" in capsys.readouterr().err


def test_tier_secrets_are_scoped_to_the_matching_child(monkeypatch):
    monkeypatch.setenv("HUB_TIER_LITERATURE__API_KEY", "placeholder-secret")
    monkeypatch.setenv("HUB_TIER_VULNS__API_KEY", "another-placeholder")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    literature = tier_environment("literature")
    assert literature.items() >= {"API_KEY": "placeholder-secret"}.items()
    assert "another-placeholder" not in literature.values()
    assert literature["PATH"] == "/usr/bin:/bin"
    assert "HOME" in literature
    local = tier_environment("local-code")
    assert local.get("API_KEY") is None
    assert local["PATH"] == "/usr/bin:/bin"


def test_fetch_truncates_at_500_kib_and_reports_note(monkeypatch):
    payload = b"x" * (600 * 1024)

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/plain", "content-length": str(len(payload))}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def raise_for_status(self):
            return None

        async def aiter_bytes(self):
            yield payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("hub.fetch.httpx.AsyncClient", FakeClient)
    result = asyncio.run(fetch_url("https://example.invalid/", internal=True))
    assert result["bytes"] == MAX_BYTES
    assert len(result["text"].encode()) == MAX_BYTES
    assert "truncated" in result["note"].lower()


def test_fetch_strips_scripts_and_rejects_non_text(monkeypatch):
    class FakeResponse:
        status_code = 200

        def __init__(self, content_type, payload):
            self.headers = {"content-type": content_type}
            self.payload = payload

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def raise_for_status(self):
            return None

        async def aiter_bytes(self):
            yield self.payload

    class FakeClient:
        response = FakeResponse("text/html", b"<p>keep</p><script>drop()</script><style>drop</style>")

        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, *args, **kwargs):
            return self.response

    monkeypatch.setattr("hub.fetch.httpx.AsyncClient", FakeClient)
    result = asyncio.run(fetch_url("https://example.invalid/", internal=True))
    assert result["text"] == "keep"

    FakeClient.response = FakeResponse("application/pdf", b"pdf")
    with pytest.raises(FetchError, match="non-text"):
        asyncio.run(fetch_url("https://example.invalid/", internal=True))


def test_loopback_fetch_is_refused_without_internal_flag(make_client):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
    with make_client({}) as client:
        response = client.get("/api/fetch", params={"url": "http://127.0.0.1:8471/"})
        assert response.status_code == 403
        allowed = client.get("/api/fetch", params={"url": f"http://127.0.0.1:{free_port}/", "internal": "true"})
        assert allowed.status_code == 502


def test_pin_and_watch_routes_store_only(make_client):
    with make_client({}) as client:
        pin = client.post("/api/pin", json={"item": {"title": "Pinned"}})
        assert pin.status_code == 200
        pin_id = pin.json()["id"]
        assert client.get("/api/pins").json()["pins"][0]["id"] == pin_id
        assert client.delete(f"/api/pin/{pin_id}").json()["deleted"] is True
        created = client.post("/api/watch", json={"query": "  incident response  "})
        assert created.status_code == 200
        assert created.json()["query"] == "incident response"
        assert client.get("/api/watch").json()["watches"][0]["id"] == created.json()["id"]


def test_health_nested_tiers_wins_and_colliding_names_land_in_tier_meta(make_client):
    with make_client(stub_config("tiers")) as client:
        health = client.get("/api/health").json()
        assert health["tiers"]["tiers"]["state"] == "ok"
        assert health["tier_meta"]["tiers"]["state"] == "ok"
        assert health["cache_ttl"] == 900
        assert "literature" not in health

    with make_client(stub_config("cache_ttl")) as client:
        health = client.get("/api/health").json()
        assert health["cache_ttl"] == 900
        assert health["tiers"]["cache_ttl"]["state"] == "ok"
        assert health["tier_meta"]["cache_ttl"]["state"] == "ok"

    with make_client(stub_config("plain")) as client:
        health = client.get("/api/health").json()
        assert "tier_meta" not in health
        assert health["plain"]["state"] == "ok"
