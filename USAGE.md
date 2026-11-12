# Using research-hub

A practical guide to running the host, searching tiers, building a local
reading corpus, and asking questions over it.

---

## 1. Start the host

```bash
cd research-hub
source .venv/bin/activate
export HUB_STATE="$HOME/research-hub-state"   # if not already in your profile
python -m hub
```

You'll see uvicorn log lines ending with:

```
INFO:     Uvicorn running on http://127.0.0.1:8471 (Press CTRL+C to quit)
```

The host binds **only** to loopback — it is not reachable from other machines,
by design. Open **http://127.0.0.1:8471** in a browser to see the dashboard.

Stop it with `Ctrl+C`. State survives restarts; tiers are started fresh on the
next search.

## 2. The dashboard (three panes, maybe four)

The page has a search form on top and exactly three panes below it. The
panes are by tier, not by function — each tier's results land in the pane its
name matches:

1. **Literature** — tiers named like literature, papers, books, archives, or
   journals.
2. **Vulnerabilities** — tiers named like vulnerabilities, CVEs, or security.
3. **Local code** — tiers named like code, repos, or local.

A tier that matches no pane lands in Literature unless the fourth pane is
enabled. Health is shown inside each pane as a per-tier status dot and state
(`ok`, `degraded`, `skipped`, `absent`), with notes; the full picture is
available as JSON from `/api/health`, including the cache TTL (900 s).

Pins are API-only: there is no pins pane on the dashboard. Pin, list, and
delete through `/api/pin` and `/api/pins` (see §5).

A fourth pane ("Other tiers") exists behind `HUB_FOURTH_PANE=1` (set it
before starting the host if you want it). Everything the dashboard shows is
also available as JSON (see below), so you can script everything.

## 3. Search across tiers

**In the browser:** type into the search form at the top and press enter.

**From the command line / scripts:**

```bash
curl -s 'http://127.0.0.1:8471/api/search?query=surface+codes' | python3 -m json.tool
```

Response shape:

```json
{
  "results": [ {"tier": "annas", "title": "...", "url": "...", "author": "...", ...} ],
  "notes":   { "annas": {"state": "ok", "note": ""}, "rag": {"state": "ok", "note": ""} }
}
```

- Every registered tier is queried **concurrently**, each with a
  `HUB_TIER_TIMEOUT` deadline (default 12 s).
- A tier that fails, times out, or exits still shows up in `notes` — it never
  breaks the other results.
- Results are deduplicated by **lowercased alphanumeric title, truncated to 60
  characters** (title only — authors never influence dedupe).
- Identical queries within 900 seconds are served from cache. Use a slightly
  different query (or restart) to bypass.

**Check tier health anytime:**

```bash
curl -s http://127.0.0.1:8471/api/health | python3 -m json.tool
```

Every registered tier is always listed, even if it never answered.

## 4. Fetching a page through the host

```bash
curl -s 'http://127.0.0.1:8471/api/fetch?url=https%3A%2F%2Fexample.com%2Fpage' | python3 -m json.tool
```

Guardrails, so you know what it will refuse:

- **500 KiB maximum** response size (larger pages are truncated with a note).
- **20 second** timeout.
- **http(s) only** — no `file:`, `ftp:`, etc.
- **Loopback refused** unless you pass `internal=1` (a deliberate escape hatch
  for local development).

For anything big (books, PDFs) use the RAG tier's own downloader instead — it
allows up to 250 MiB. See §6.

## 5. Pins: your reading queue

```bash
# pin something (body is the item JSON you want to keep)
curl -s -X POST http://127.0.0.1:8471/api/pin \
     -H 'Content-Type: application/json' \
     -d '{"title": "Surface Codes", "url": "https://arxiv.org/abs/..."}'

# list pins
curl -s http://127.0.0.1:8471/api/pins

# delete a pin by its id (the `id` field returned by POST /api/pin)
curl -s -X DELETE http://127.0.0.1:8471/api/pin/<id>
```

Pins are stored server-side and listed by `GET /api/pins`; there is no pins pane on the dashboard.

## 6. The Anna's Archive tier

Registered out of the box (`mcp_servers.json` → `annas`). It signs in with
`ANNAS_KEY` if you set one; without a key, search still works on open mirrors.

**Behavior worth knowing:**

- If the mirror answers with a bot challenge, you get `{"results": [],
  "note": "challenge"}` rather than garbage — retry later or change
  `HUB_TIER_ANNAS__ANNAS_MIRROR`.
- `download(md5)` streams the file to `ANNAS_STORE` (default
  `<HUB_STATE>/annas`) with a **250 MiB cap**, and reports the saved path.
- Results are deduplicated by md5, so mirror duplicates collapse.
- `pin_result` writes into the same pin store the host serves.

**Set your key without committing it:**

Assign your account key to the variable `HUB_TIER_ANNAS__ANNAS_KEY`
(`ANNAS_KEY`, scoped to this tier — see the env table in INSTALL.md) in your
shell profile or secret manager. Never paste the value into any file in this
repository; the selfcheck fails if a key-shaped string is ever committed.

## 7. The RAG tier: build a local, searchable corpus

The `rag` tier turns PDFs, EPUBs, text files (and DjVu, with `djvutxt`) into a
local vector + full-text index at `<HUB_STATE>/rag.sqlite3`, then answers
questions **with citations** from that corpus only.

### Ingest documents

```bash
# via the host API is not how this works — ingestion goes through the tier.
```

From Python (or any script on this machine):

```python
from pathlib import Path
from lib.rag.ingest import ingest_document, ingest_url

ingest_document(Path("~/papers/attention.pdf").expanduser())
ingest_url("https://arxiv.org/pdf/1706.03762", title="Attention Is All You Need")
```

What happens: download (own downloader, 250 MiB cap) → extract → chunk
(sliding windows that may span page breaks; each chunk remembers its start
page) → embed → store. If fewer than 25 % of a PDF's pages contain embedded
text it's flagged `ScannedDoc`; install tesseract and run the OCR path instead.

Time windows: set `INGEST_WINDOWS="02:00-05:00"` to restrict ingestion to those
UTC hours; `22:00-02:00` style windows that cross midnight work correctly. A
temporary override file at `<HUB_STATE>/ingest-override.json`
(`{"until": <unix-epoch>, "reason": "bulk import"}`) opens ingestion regardless
of windows until it expires.

### Search and ask

```bash
curl -s 'http://127.0.0.1:8471/api/search?query=depolarizing+noise' | python3 -m json.tool
```

The tier exposes two research tools beyond the required five:

- **`rag_ask(question, mode, limit)`** — retrieves passages and asks your LLM
  to answer *only* from them, returning numbered citations with `doc_id` and
  `page`. Modes: `vector`, `bm25`, `hybrid` (reciprocal-rank fusion, k=60),
  `hybrid_rerank` (default; blends the cross-encoder score at weight 0.7).
- **`rag_index(source, title)`** — ingest a URL or local file.

`rag_ask` needs an OpenAI-compatible endpoint:

```bash
export LLM_BASE_URL="https://api.openai.com/v1"   # or any compatible server
export LLM_MODEL="gpt-4o-mini"
# set LLM_API_KEY the same way (environment only, never in files)
```

No LLM configured? `rag_ask` still returns the retrieved passages as
citations with an empty answer — retrieval works without any model.

Transient LLM errors (429/5xx) are retried automatically; after retries it
raises `LLMError` rather than inventing an answer. A malformed response
degrades to a note instead of crashing.

### Maintenance tools

`eval_rag.py` and `golden_coverage.py` are CLIs; `reindex` and `curate` are
Python modules you call from a script. All operate on your `HUB_STATE`
database:

```python
# Re-embed the whole corpus after a model change (resumable + idempotent:
# failures leave documents untouched, and the daily counter isn't inflated)
import lib.rag.db as rag_db
from lib.rag.tools import reindex, curate

conn = rag_db.open_db()
print(reindex.reindex(conn, embedder))          # {"reindexed": n, "failures": []}

# Export the corpus (md5-keyed) and import it elsewhere;
# pending pins ride along and unknown md5s land in pending_pins
print(curate.export(conn, "/backup/corpus.json"))
print(curate.import_docs(conn, "/backup/corpus.json", embedder))
print(curate.prune_pending(conn))               # drain the pin queue

# Guarded delete (ShrinkBlocked past the 24h baseline unless force=True)
print(curate.remove(conn, "0123...ef", force=False))
```

```bash
# Retrieval quality: nDCG / MRR / recall@k with a bootstrap confidence
# interval; exits non-zero when --min-ndcg isn't met (CI-gateable)
python -m lib.rag.tools.eval_rag --golden golden.json --db "$HUB_STATE/rag.sqlite3" --min-ndcg 0.8

# Which golden questions have their source doc in the corpus?
python -m lib.rag.tools.golden_coverage --golden golden.json --db "$HUB_STATE/rag.sqlite3"
```

Golden files are JSON: either a bare list or `{"queries": [{"question": ...,
"md5": ...}, ...]}`.

### Deleting documents safely

Removal is guarded: a delete that would exceed the last-24 h ingestion baseline
is blocked with `ShrinkBlocked` (the error carries the numbers). Pass `force`
to override — the guard exists so a buggy loop can't empty your corpus.

## 8. Adding your own tier (drop-in, zero host changes)

Create a small MCP server exposing the five required tools
(`search`, `fetch_page`, `pin_result`, `pinned`, `unpin`), then add one entry
to `mcp_servers.json`:

```json
"mytier": {
  "command": "uv",
  "args": ["run", "--with", "mcp[cli]<2,httpx", "python",
           "{{DEPLOY_DIR}}/servers/my_server.py"]
}
```

Restart the host. That's the whole integration — the host discovers the tier's
name from the registry key, passes a per-tier environment (see
`hub/registry.py`), and merges its results. `tests/test_dropin.py` proves that
registering a new name requires **no code changes** anywhere else. Tier pins
`mcp<2` in its args; the host refuses to start otherwise (exit code 2).

## 9. Daily-driver cheat sheet

```bash
python -m hub                                  # start the host
curl -s '127.0.0.1:8471/api/search?query=…'    # search everything
curl -s  127.0.0.1:8471/api/health             # tier status
curl -s  127.0.0.1:8471/api/pins               # reading queue
pytest -q                                      # offline test suite
./scripts/selfcheck.sh                          # full preflight
```

## 10. Rules the system enforces (so you don't have to)

- One listener: `127.0.0.1:8471` (or your `HUB_PORT`). No sidecars, no extra ports.
- All state under `HUB_STATE`; your home directories are never touched.
- `/api/fetch`: 500 KiB / 20 s / http(s)-only / loopback blocked without `internal=1`.
- Cache: 900 s TTL, 500-entry LRU.
- Dedupe: lowercased-alphanumeric title, 60 chars, title only.
- Health always lists every registered tier.
- Dashboard: three panes; a fourth only with `HUB_FOURTH_PANE=1`.
- Ingestion windows and the 24 h shrink guard protect your corpus from
  accidents, including from you at 3 a.m.

Full invariant→test mapping lives in **GUARDRAILS.md**; the tier interface
contract lives in **CONTRACT.md**.
