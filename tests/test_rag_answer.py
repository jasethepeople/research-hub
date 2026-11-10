import pytest

from lib.rag.answer import answer, build_prompt
from lib.rag.embed import hash_embed


def test_answer_cites_only_when_llm_available(corpus):
    def fake_complete(prompt: str) -> str:
        return "Surface codes help. [1]"

    outcome = answer(
        corpus,
        "surface codes depolarizing",
        embedder=hash_embed,
        complete=fake_complete,
    )
    assert outcome["answer"] == "Surface codes help. [1]"
    assert outcome["note"] == ""
    assert outcome["citations"][0]["n"] == 1
    assert outcome["citations"][0]["title"]


def test_answer_reports_llm_unavailable_without_fabricating(corpus):
    def broken_complete(prompt: str) -> str:
        raise RuntimeError("no endpoint configured")

    outcome = answer(corpus, "radio bearings", embedder=hash_embed, complete=broken_complete)
    assert outcome["answer"] == ""
    assert outcome["note"].startswith("llm_unavailable")
    assert outcome["citations"], "citations must still be returned"


def test_answer_no_passages(corpus):
    outcome = answer(corpus, "zzzqqq", embedder=hash_embed, complete=lambda prompt: "x")
    assert outcome == {"answer": "", "citations": [], "note": "no passages retrieved"}


def test_prompt_demands_citations():
    prompt = build_prompt("q", [{"n": 1, "title": "T", "text": "body", "md5": "m"}])
    assert "[1]" in prompt
    assert "ONLY" in prompt.upper()


def test_answer_with_no_passages_never_calls_the_llm(corpus):
    calls = []

    def must_not_run(prompt: str) -> str:
        calls.append(prompt)
        raise AssertionError("LLM must not be called without passages")

    outcome = answer(corpus, "zzzqqq", embedder=hash_embed, complete=must_not_run)
    assert outcome == {"answer": "", "citations": [], "note": "no passages retrieved"}
    assert calls == []


def test_llm_complete_retries_on_500_then_succeeds():

    import httpx

    from lib.rag.answer import llm_complete

    def handler(request: httpx.Request) -> httpx.Response:
        handler.attempts += 1
        if handler.attempts < 3:
            return httpx.Response(500, text="boom")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok [1]"}}]},
        )

    handler.attempts = 0
    transport = httpx.MockTransport(handler)
    text = llm_complete(
        "prompt",
        base_url="http://llm.test/v1",
        api_key="k",
        transport=transport,
        sleep=lambda seconds: None,
    )
    assert text == "ok [1]"
    assert handler.attempts == 3


def test_llm_complete_gives_up_after_retries_and_raises_llm_error():
    import httpx

    from lib.rag.answer import LLMError, llm_complete

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    with pytest.raises(LLMError):
        llm_complete(
            "prompt",
            base_url="http://llm.test/v1",
            transport=httpx.MockTransport(handler),
            sleep=lambda seconds: None,
        )


def test_llm_complete_malformed_body_raises_llm_error():
    import httpx

    from lib.rag.answer import LLMError, llm_complete

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    with pytest.raises(LLMError):
        llm_complete(
            "prompt",
            base_url="http://llm.test/v1",
            transport=httpx.MockTransport(handler),
        )


def test_answer_survives_a_malformed_llm_response(corpus, monkeypatch):

    import httpx

    import lib.rag.answer as answer_module

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="{not json")

    monkeypatch.setattr(
        answer_module,
        "llm_complete",
        lambda prompt: answer_module.llm_complete(
            prompt,
            base_url="http://llm.test/v1",
            transport=httpx.MockTransport(handler),
            sleep=lambda seconds: None,
        ),
    )
    outcome = answer(corpus, "radio bearings", embedder=hash_embed)
    assert outcome["answer"] == ""
    assert outcome["note"]
    assert "llm" in outcome["note"].lower() or "error" in outcome["note"].lower()
    assert outcome["citations"], "citations must survive an LLM failure"


def test_citations_carry_doc_id_and_page(corpus):

    from lib.rag.answer import answer

    outcome = answer(
        corpus,
        "radio bearings",
        embedder=hash_embed,
        complete=lambda prompt: "HF radio bearings. [1]",
    )
    citation = outcome["citations"][0]
    assert citation["doc_id"]
    assert len(citation["doc_id"]) == 16
    assert citation["page"] >= 1
