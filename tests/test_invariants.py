import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from hub.cache import CACHE_MAXSIZE, CACHE_TTL
from hub.config import DEFAULT_STATE_DIR, Settings
from hub.fetch import MAX_BYTES, TIMEOUT_SECONDS, FetchError, fetch_url
from hub.orchestrator import title_key
from hub.storage import Store
from tests.conftest import stub_config

REPO = Path(__file__).resolve().parent.parent
CODE_DIRS = ("hub", "servers", "lib", "tests", "scripts")
HOME_MARKS = ("/" "home" "/", "/" "Users" "/", "~/" "code")

SECRET_PATTERNS = [
    "s" "k-",
    "K" "EY=",
    "TOK" "EN=",
    "SECRET" "=",
    "PASSW" "ORD=",
    "gh" "p_",
    "github_" "pat_",
    "AK" "IA",
    "AI" "za",
    "gl" "pat_",
    "xo" "xb-",
    "sk-" "ant-",
    "HF_" "TOKEN",
]


def _tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True)
    return [REPO / line for line in out.stdout.splitlines() if line]


def _files_under(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.rglob("*")))
        else:
            files.append(path)
    return [path for path in files if path.is_file()]


def _iter_source_lines(paths):
    for path in paths:
        if path.stat().st_size > 1_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            yield path, number, line


def test_i1_only_loopback_listens(monkeypatch, tmp_path):
    if not Path("/proc/net/tcp").exists():
        pytest.skip("Linux TCP tables unavailable")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    empty_registry = tmp_path / "registry.json"
    empty_registry.write_text("{}", encoding="utf-8")
    env = os.environ | {
        "HUB_PORT": str(port),
        "HUB_STATE": str(tmp_path / "state"),
        "HUB_MCP_SERVERS": str(empty_registry),
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "hub"],
        cwd=REPO,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 30
        up = False
        while time.monotonic() < deadline and not up:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as response:
                    up = response.status == 200
            except OSError:
                time.sleep(0.3)
        assert up, "server did not come up on 127.0.0.1"
        listeners = []
        for table in ("/proc/net/tcp", "/proc/net/tcp6"):
            for row in Path(table).read_text().splitlines()[1:]:
                columns = row.split()
                if columns[3] != "0A":
                    continue
                address_hex, port_hex = columns[1].split(":")
                if int(port_hex, 16) != port:
                    continue
                raw = bytes.fromhex(address_hex)
                if len(raw) == 4:
                    listeners.append(socket.inet_ntop(socket.AF_INET, raw[::-1]))
                else:
                    raw = b"".join(raw[index : index + 4][::-1] for index in range(0, 16, 4))
                    listeners.append(socket.inet_ntop(socket.AF_INET6, raw))
        assert listeners, "expected the hub listener to be visible"
        assert set(listeners) == {"127.0.0.1"}, listeners
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_i2_no_secrets_in_committed_files():
    offenders = [
        f"{path}:{number}: {line.strip()[:80]}"
        for path, number, line in _iter_source_lines(_tracked_files())
        if any(pattern in line for pattern in SECRET_PATTERNS)
    ]
    assert offenders == [], offenders


def test_i3_mcp_1x_only_in_registry_and_pyproject():
    registry = json.loads((REPO / "mcp_servers.json").read_text(encoding="utf-8"))
    assert registry, "expected shipped tiers to be registered"
    for name, spec in registry.items():
        joined = " ".join(spec.get("args", []))
        assert "mcp[cli]<2" in joined or "mcp<2" in joined, f"tier {name} does not pin mcp<2"
    assert "mcp[cli]<2" in (REPO / "pyproject.toml").read_text(encoding="utf-8")


def test_i4_no_absolute_home_paths_or_user_code_reference():
    offenders = []
    for path, number, line in _iter_source_lines(_files_under([REPO / name for name in CODE_DIRS])):
        if any(mark in line for mark in HOME_MARKS):
            offenders.append(f"{path}:{number}")
    assert offenders == [], offenders


def test_i5_all_state_lives_under_hub_state(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setenv("HUB_STATE", str(state))
    store = Store(state)
    store.initialize()
    store.pin({"title": "state check"})
    assert (state / "hub.sqlite3").is_file()

    import importlib

    annas = importlib.import_module("lib.annas")
    rag_db = importlib.import_module("lib.rag.db")
    assert annas.default_store_dir() == state / "annas-store"
    assert rag_db.state_db_path() == state / "rag.sqlite3"
    assert DEFAULT_STATE_DIR == "~/.local/share/intel-hub"


def test_i6_fetch_guardrails(make_client):
    assert MAX_BYTES == 500 * 1024
    assert TIMEOUT_SECONDS == 20
    with pytest.raises(FetchError, match="http and https"):
        asyncio.run(fetch_url("ftp://example.invalid/file"))
    with make_client({}) as client:
        refused = client.get("/api/fetch", params={"url": "http://127.0.0.1:8471/"})
        assert refused.status_code == 403
        scheme = client.get("/api/fetch", params={"url": "ftp://example.invalid/file"})
        assert scheme.status_code == 400


def test_i7_exactly_three_panes_fourth_only_with_env(monkeypatch, make_client):
    monkeypatch.setenv("HUB_FOURTH_PANE", "0")
    assert Settings().fourth_pane is False
    monkeypatch.setenv("HUB_FOURTH_PANE", "1")
    assert Settings().fourth_pane is True
    monkeypatch.setenv("HUB_FOURTH_PANE", "0")
    with make_client({}) as client:
        assert client.get("/").text.count('<section class="pane"') == 3


def test_i8_dedupe_identity_is_lowercase_alnum_title_only(tmp_path):
    assert title_key("Hello, World!") == "helloworld"
    assert title_key("A-B! C") == title_key("a  b c")
    assert len(title_key("T" * 80)) == 60
    assert len(title_key("T" * 80 + "suffix")) == 60


def test_i9_health_lists_every_registered_tier_even_absent_ones(tmp_path, make_client):
    config = {
        **stub_config("live"),
        "ghost": {"command": sys.executable, "args": [str(tmp_path / "missing_server.py")]},
    }
    with make_client(config) as client:
        health = client.get("/api/health").json()
        assert set(health["tiers"]) == {"live", "ghost"}
        assert set(health) >= {"live", "ghost", "tiers", "cache_ttl"}
        assert health["tiers"]["ghost"]["state"] == "absent"


def test_i10_cache_ttl_900_and_lru_cap_500(make_client, monkeypatch):
    import hub.cache as cache_module

    assert CACHE_TTL == 900
    assert CACHE_MAXSIZE == 500
    with make_client({}) as client:
        cache = client.app.state.cache
        assert cache.ttl == 900
        assert cache.maxsize == 500
    cache = cache_module.ResponseCache(ttl=CACHE_TTL, maxsize=CACHE_MAXSIZE)
    cache.put(("t", "q"), {"v": 1})
    assert cache.get(("t", "q")) == {"v": 1}
    real_monotonic = cache_module.time.monotonic
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: real_monotonic() + 901)
    assert cache.get(("t", "q")) is None
    for index in range(501):
        cache.put(("t", str(index)), index)
    assert len(cache) == 500
