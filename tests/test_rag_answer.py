
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
