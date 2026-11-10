import json
import re
from pathlib import Path

import httpx
import pytest

from lib import annas
from lib.annas import AnnaArchive, ChallengeEncountered, parse_results

FIXTURE = Path(__file__).parent / "fixtures" / "search_page.html"


def handler_factory(page_html: str, account_status: int = 200, account_body: str = "signed in"):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/account/":
            return httpx.Response(account_status, text=account_body)
        if request.url.path == "/search":
            return httpx.Response(200, text=page_html)
        if request.url.path == "/dyn/api/fast_download.json":
            return httpx.Response(
                200,
                json={"download_url": str(request.url.join("/files/paper.bin"))},
            )
        if request.url.path == "/files/paper.bin":
            return httpx.Response(200, content=b"x" * 2048)
        return httpx.Response(404, text="nope")

    return handler, calls


def client_for(handler) -> AnnaArchive:
    return AnnaArchive(mirror="https://annas.test", key="test-key", transport=httpx.MockTransport(handler))


def test_parse_results_finds_six_cards():
    cards = parse_results(FIXTURE.read_text(encoding="utf-8"), limit=20)
    assert len(cards) == 6
    titles = [card["title"] for card in cards]
    assert "Introduction to Applied Cryptography" in titles
    assert all(len(card["md5"]) == 32 for card in cards)


def test_parse_results_skips_decoy_links():
    html = FIXTURE.read_text(encoding="utf-8")
    md5s = {card["md5"] for card in parse_results(html, limit=20)}
    assert "" not in md5s
    assert "2cc9f6f5c71037d3e2f4e1c8d6f3e5a7extra" not in "".join(md5s)
    assert len(md5s) == 6


def test_parse_results_handles_card_without_author():
    html = FIXTURE.read_text(encoding="utf-8")
    cards = {card["md5"]: card for card in parse_results(html, limit=20)}
    orphan = cards["3dd0a7a6d82148e4f3a5f2d9e7a4f6b8"]
    assert orphan["author"] == ""
    assert orphan["language"] == "English"
    assert orphan["format"] == "PDF"
    assert orphan["year"] == "2023"


def test_parse_results_never_raises_on_malformed_input():
    for blob in ("<a href='/md5/zzz'>", "<a>", "not html at all", "<a href=\"/md5/0x0\">T</a><div>·</div>"):
        assert parse_results(blob, limit=5) == []
    assert parse_results("", limit=5) == []


def test_parse_results_dedupes_by_md5():
    html = (
        '<a href="/md5/aaaa0000000000000000000000000001">First Title</a><div>One</div>'
        '<div>English · PDF · 1 MB · 2020</div>'
        '<a href="/md5/aaaa0000000000000000000000000001">First Title</a><div>One</div>'
        '<div>English · EPUB · 1 MB · 2020</div>'
    )
    cards = parse_results(html, limit=20)
    assert len(cards) == 1


def test_search_signs_in_and_returns_results():
    handler, calls = handler_factory(FIXTURE.read_text(encoding="utf-8"))
    archive = client_for(handler)
    outcome = archive.search("cryptography", limit=5)
    assert outcome["note"] == ""
    assert len(outcome["results"]) == 5
    assert outcome["results"][0]["url"].startswith("https://annas.test/md5/")
    assert any(request.url.path == "/account/" for request in calls)


def test_search_401_returns_challenge_note():
    handler, _ = handler_factory(FIXTURE.read_text(encoding="utf-8"), account_status=401)
    archive = client_for(handler)
    outcome = archive.search("anything")
    assert outcome == {"results": [], "note": "challenge"}


def test_search_challenge_body_returns_challenge_note():
    handler, _ = handler_factory("Just a moment — challenge page", account_body="ok")
    archive = client_for(handler)
    outcome = archive.search("anything")
    assert outcome["results"] == []
    assert outcome["note"] == "challenge"


def test_search_challenge_raises_when_strict():
    handler, _ = handler_factory(FIXTURE.read_text(encoding="utf-8"), account_status=403)
    archive = client_for(handler)
    with pytest.raises(ChallengeEncountered):
        archive.search("anything", strict=True)


def test_search_caches_for_900s():
    handler, calls = handler_factory(FIXTURE.read_text(encoding="utf-8"))
    archive = client_for(handler)
    first = archive.search("same query")
    second = archive.search("same query")
    assert first == second
    search_calls = [request for request in calls if request.url.path == "/search"]
    assert len(search_calls) == 1


def test_download_streams_to_store_and_respects_cap(tmp_path):
    handler, _ = handler_factory(FIXTURE.read_text(encoding="utf-8"))
    archive = client_for(handler)
    archive.store_dir = tmp_path / "store"
    outcome = archive.download("aaaa0000000000000000000000000001")
    saved = tmp_path / "store" / "aaaa0000000000000000000000000001.bin"
    assert outcome["saved"] is True
    assert saved.read_bytes() == b"x" * 2048


def test_download_truncates_at_cap(tmp_path, monkeypatch):
    import lib.annas as annas_module

    handler, _ = handler_factory(FIXTURE.read_text(encoding="utf-8"))
    archive = client_for(handler)
    archive.store_dir = tmp_path / "store"
    monkeypatch.setattr(annas_module, "DOWNLOAD_CAP", 1024)
    outcome = archive.download("aaaa0000000000000000000000000001")
    assert outcome["saved"] is True
    assert outcome["bytes"] == 1024
    assert "250" in outcome["note"]


def test_pin_unpin_round_trip():
    handler, _ = handler_factory(FIXTURE.read_text(encoding="utf-8"))
    archive = client_for(handler)
    pin = archive.pin_result({"title": "Keep me", "md5": "aaaa0000000000000000000000000001"})
    pin_id = pin["id"]
    assert len(archive.pinned()) == 1
    removal = archive.unpin(pin_id)
    assert removal["removed"] is True
    assert archive.pinned() == []


def test_search_result_shape_matches_contract():
    handler, _ = handler_factory(FIXTURE.read_text(encoding="utf-8"))
    archive = client_for(handler)
    outcome = json.loads(json.dumps(archive.search("x")))
    for item in outcome["results"]:
        assert isinstance(item["title"], str)
        assert isinstance(item["author"], str)
        assert isinstance(item["url"], str)


REAL_FIXTURE = Path(__file__).parent / "fixtures" / "search_page_real.html"


@pytest.mark.skipif(
    not REAL_FIXTURE.exists(),
    reason="real search page not captured yet (see tests/fixtures/REPOINT.md)",
)
@pytest.mark.parametrize("fixture", [FIXTURE, REAL_FIXTURE], ids=["synthesized", "real-gd"])
def test_parser_fixture_has_valid_results(fixture):
    html = fixture.read_text(encoding="utf-8", errors="replace")
    parsed = annas.parse_results(html, limit=50)
    minimum = 40 if fixture == REAL_FIXTURE else 6
    assert len(parsed) >= minimum
    assert all(re.fullmatch(r"[0-9a-f]{32}", item["md5"]) for item in parsed)
    assert all(item["title"].strip() for item in parsed)


def test_parse_results_passes_against_real_markup():
    """Captured live from https://annas-archive.gd/search?q=clean+code&display=table

    (2026-11-10, via a real browser session; .gd was still serving the classic
    /md5/ results TABLE layout, not /books/<id>-<slug> cards). The fixture is
    the extracted results <table> only - a search-results page, not a detail
    page or a mirror interstitial. Band assert: a healthy table parses 20-50
    rows at limit=50; "> 0" alone would pass on a single stray anchor.
    """
    html = REAL_FIXTURE.read_text(encoding="utf-8", errors="replace")
    assert len(html) > 20_000, f"real fixture unexpectedly small: {len(html)} bytes"
    assert re.search(r'href=["\']/md5/[0-9a-fA-F]{32}', html), "expected a stable md5 anchor"
    assert "DDoS-Guard" not in html and "cf-browser-verification" not in html
    parsed = annas.parse_results(html, limit=50)
    assert isinstance(parsed, list)
    assert 20 <= len(parsed) <= 50, f"real fixture should parse 20-50 rows, got {len(parsed)}"
    for item in parsed:
        assert re.fullmatch(r"[0-9a-f]{32}", item["md5"])
        assert item["title"].strip()
        assert item["md5"] in item["url"]
