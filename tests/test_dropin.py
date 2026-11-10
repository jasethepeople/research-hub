"""Drop-in gate: a new tier is a registry entry and nothing else.

For each of the three names below, a stub registered under that name must
load, answer /api/search, appear in /api/health with state ok, and need zero
host changes. The host source must not mention the tier names at all.
"""

import json
import sys
from pathlib import Path

from tests.conftest import STUB, stub_config

TIER_NAMES = ("literature", "vulns", "localcode")


def test_each_tier_name_loads_individually(make_client):
    for name in TIER_NAMES:
        with make_client(stub_config(name)) as client:
            body = client.get("/api/search", params={"query": "anything"}).json()
            assert body["results"], f"{name}: no results"
            assert body["results"][0]["tier"] == name
            assert body["notes"][name]["state"] == "ok"
            health = client.get("/api/health").json()
            assert health["tiers"][name]["state"] == "ok"
            assert health[name]["state"] == "ok"
            assert health["cache_ttl"] == 900


def test_all_three_tiers_registered_together(make_client):
    config: dict = {}
    for name in TIER_NAMES:
        config.update(stub_config(name))
    with make_client(config) as client:
        health = client.get("/api/health").json()
        assert set(health["tiers"]) == set(TIER_NAMES)
        for name in TIER_NAMES:
            assert health["tiers"][name]["state"] == "ok"
        body = client.get("/api/search", params={"query": "dedupe"}).json()
        # identical fixture results dedupe onto the first registry tier
        assert body["results"][0]["tier"] == "literature"
        assert body["results"][0]["also_on"] == ["vulns", "localcode"]
        for name in TIER_NAMES:
            assert body["notes"][name]["state"] == "ok"


def test_registry_entries_are_the_only_host_input(tmp_path):
    config: dict = {}
    for name in TIER_NAMES:
        config.update(stub_config(name))
    registry_path = tmp_path / "mcp_servers.json"
    registry_path.write_text(json.dumps(config), encoding="utf-8")
    loaded = json.loads(registry_path.read_text(encoding="utf-8"))
    for name in TIER_NAMES:
        entry = loaded[name]
        assert entry["command"] == sys.executable
        assert str(STUB) in " ".join(entry["args"])


def test_host_source_never_names_the_tiers():
    repo = Path(__file__).resolve().parent.parent
    host_files = sorted((repo / "hub").glob("*.py")) + sorted((repo / "servers").glob("*.py"))
    for path in host_files:
        text = path.read_text(encoding="utf-8")
        for name in TIER_NAMES:
            assert name not in text, f"{path.name} hardcodes tier name {name!r}"
