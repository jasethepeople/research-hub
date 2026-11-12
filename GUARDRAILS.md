# Guardrails: invariants, enforcement, and proof

Every absolute invariant is enforced in running code and exercised by a test in
`tests/test_invariants.py` (plus supporting tests where noted). The tests run
the real app — through `make_client` (ASGI) or a spawned `python -m hub`
process — not against comments.

## Invariant table

| Invariant | Where it is enforced | The test that proves it |
| --- | --- | --- |
| I1 — exactly one listener, on the configured host (HUB_HOST, default 127.0.0.1); no extra port, sidecar, or process outside MCP stdio | `hub/config.py` (HUB_HOST, default `127.0.0.1`; single `HUB_PORT` default 8471), `hub/app.py` main() binds the configured host; tiers are stdio children started by `hub/registry.py` | `test_i1_only_loopback_listens` spawns `python -m hub` with the default host and with explicit `HUB_HOST=127.0.0.1`, and asserts every TCP listener for the chosen port (read from `/proc/net/tcp*`) is bound to the configured host |
| I2 — no secret in any committed file | Operator-supplied environment only; `scripts/selfcheck.sh` secret scan; `hub/registry.py` passes only prefixed/allowlisted env vars to children | `test_i2_no_secrets_in_committed_files` scans every git-tracked file for provider token prefixes and uppercase assignment patterns; selfcheck re-scans the registry |
| I3 — mcp is 1.x only, pinned in every registry entry; guard exits 2 | `pyproject.toml` (`mcp[cli]<2`), `mcp_servers.json` args, `hub/registry.py::assert_mcp_v1` | `test_i3_mcp_1x_only_in_registry_and_pyproject` checks every registry entry and pyproject; `test_version_guard_exits_2_for_mcp_v2` (tests/test_host.py) asserts `SystemExit(2)` |
| I4 — no absolute `/home/` or `/Users/` paths in `hub/`, `servers/`, `lib/`, `tests/`, `scripts/` | Paths derive from `hub/config.py::DEPLOY_DIR` and env vars; tiers receive `{{DEPLOY_DIR}}` substitution | `test_i4_no_absolute_home_paths_or_user_code_reference` scans all five source trees line by line (also rejects `~/code` references) |
| I5 — `~/code` untouched; all state under `HUB_STATE` | `hub/config.py` (state default `~/.local/share/intel-hub`), `lib/annas.py::default_store_dir`, `lib/rag/db.py::state_db_path` | `test_i5_all_state_lives_under_hub_state` pins hub SQLite, the annas store, and the rag database under a temp `HUB_STATE` |
| I6 — `/api/fetch` stays 500 KiB / 20 s / http(s)-only / loopback refused without `internal=1` | `hub/fetch.py` (`MAX_BYTES`, `TIMEOUT_SECONDS`, `_check_url`), `hub/app.py` route | `test_i6_fetch_guardrails` plus `test_fetch_truncates_at_500_kib_and_reports_note`, `test_loopback_fetch_is_refused_without_internal_flag` (tests/test_host.py) |
| I7 — dashboard renders exactly three panes; fourth only with `HUB_FOURTH_PANE=1` | `hub/index.html` (three static `<section class="pane">`; JS appends the fourth only when the flag is true), `hub/app.py`, `hub/config.py` | `test_i7_exactly_three_panes_fourth_only_with_env` checks the setting and the served HTML in both modes |
| I8 — dedupe identity is the lowercased alphanumeric title, truncated to 60 chars; author never joins | `hub/orchestrator.py::title_key` and the merge loop in `search_all` | `test_i8_dedupe_identity_is_lowercase_alnum_title_only` plus `test_dedupe_keeps_first_registry_tier_and_records_other` (tests/test_host.py) |
| I9 — `/api/health` always lists every registered tier | `hub/app.py::health` (built from `Registry.health()`; even `absent`/`skipped` tiers appear), `hub/registry.py::load` | `test_i9_health_lists_every_registered_tier_even_absent_ones` registers a live tier and a tier whose server file is missing |
| I10 — cache TTL 900 s, LRU cap 500 | `hub/cache.py` (`CACHE_TTL`, `CACHE_MAXSIZE`), `hub/app.py` lifespan | `test_i10_cache_ttl_900_and_lru_cap_500` checks constants, the app instance, TTL expiry under a fake clock, and eviction at 500 |

## Files touched and why

- `hub/registry.py` — F1: `tier_environment()` now merges the `PASSTHROUGH_ENV_KEYS` allowlist (PATH, HOME, LANG, LC_ALL, TMPDIR, TZ, UV_CACHE_DIR, UV_PYTHON, UV_OFFLINE, SSL_CERT_FILE) beneath the stripped tier variables so children keep a working `uv`.
- `hub/app.py` — F2: `/api/health` mirrors every tier at the top level while keeping the nested `tiers` shape and `cache_ttl`.
- `hub/config.py` — env-derived `Settings` via `default_factory` (so I1/I4/I5 hold at any deployment path), exported `DEFAULT_STATE_DIR`/`DEFAULT_PORT` constants.
- `hub/cache.py` — unchanged TTL/LRU constants; referenced by the invariant test (no behavior change).
- `tests/test_host.py` — updated the tier-environment test from exact equality to a subset assertion and added the top-level health mirror test.
- `tests/test_invariants.py` — one test per absolute invariant, run against the live app or a spawned host process.
- `tests/conftest.py` — shared `make_client` plus a `corpus` fixture and skip helpers for the RAG extras.
- `tests/fixtures/search_page.html` — synthesized Anna's Archive results page: 6 cards, 2 decoy links, 1 card without an author, one duplicate md5.
- `tests/test_annas.py` — parser purity/decoys/dedupe, sign-in, challenge notes, 900 s cache, capped download, pin round-trip, and an end-to-end search through the running host against a local fake mirror.
- `lib/annas.py` — Deliverable A logic: pure `parse_results(html, limit)`, cookie-jar sign-in, challenge detection, 900 s/200-entry cache, 250 MiB capped streaming downloads, in-memory pins.
- `servers/annas_server.py` — Deliverable A thin FastMCP wrapper (five required tools plus `download`) over `lib/annas.py`.
- `lib/rag/db.py` — Deliverable B storage: `HUB_STATE/rag.sqlite3`, sqlite-vec loaded, WAL, `assert_model`/`EmbedMismatch`, `doc_id = sha1(md5)[:16]`, meta/corpus/chunks/FTS5+triggers/vec0/corpus_daily/pending_pins tables.
- `lib/rag/extract.py` — pdf/epub/djvu/txt extraction with `ScannedDoc` when fewer than 25 % of pages carry text.
- `lib/rag/ocr.py` — tesseract at 300 dpi with a confidence gate and a JSON cache; raises `OcrUnavailable` when tesseract is absent so tests skip cleanly.
- `lib/rag/chunk.py` — paragraph-aware sliding-window chunking with overlap.
- `lib/rag/embed.py` — fastembed default embedder, plus deterministic token-averaged hash vectors (384 floats) so tests never download a model.
- `lib/rag/rerank.py` — lexical reranker, optional cross-encoder, RRF blend weight 0.7.
- `lib/rag/retrieve.py` — `vector | bm25 | hybrid | hybrid_rerank` retrieval; RRF k=60; hybrid_rerank blends rerank score 0.7 with normalized retrieval rank.
- `lib/rag/answer.py` — cite-only prompt, `llm_complete` against an OpenAI-compatible `LLM_BASE_URL`, `[n]` citation extraction.
- `lib/rag/guard.py` — 24 h ingestion baseline over `corpus_daily`; `ShrinkBlocked` when a prune exceeds it unless forced.
- `lib/rag/gate.py` — `INGEST_WINDOWS` parsing for ingestion time windows and the `HUB_STATE/rag-eval.lock` eval lock.
- `lib/rag/fetch.py` — the RAG tier's own downloader (250 MiB cap), deliberately separate from the host's 500 KiB `/api/fetch`.
- `lib/rag/ingest.py` — download → extract → (OCR fallback) → chunk → embed → store, recording the guard baseline.
- `lib/rag/errors.py` — shared exception types (`RagUnavailable`, `ScannedDoc`, `ShrinkBlocked`, `EvalLocked`, …).
- `lib/rag/tools/reindex.py` — full re-chunk/re-embed of the corpus with per-document failure reporting.
- `lib/rag/tools/curate.py` — md5-keyed export/import and pending-pin pruning.
- `lib/rag/tools/eval_rag.py` — nDCG/MRR/recall@k with a seeded bootstrap CI and a `--min-ndcg` exit gate.
- `lib/rag/tools/golden_coverage.py` — checks every golden question's md5 exists in the corpus.
- `servers/rag_server.py` — Deliverable B tier: five required tools plus `rag_ask` and `rag_index`; degrades to clean `unavailable` notes without the `[rag]` extra.
- `pyproject.toml` — added the optional `[rag]` dependency group (base install unchanged and light).
- `mcp_servers.json` — registered the `annas` and `rag` tiers with the fixed command shape; `rag` appends a second `--with` group for its extras.
- `scripts/selfcheck.sh` — ruff scope widened to `hub servers lib tests`, secret-scan literals split so the scanner can scan itself, still exits non-zero on any match.
- `CONTRACT.md` — documented the two shipped tiers, the extra `--with` registry convention, the env contract, and the new known gaps.
- `README.md` — pointer to the contract and guardrails (new file was empty).

## Known gaps

- The Anna's Archive fixture is synthesized: the live site is not reachable from cloud IPs, so parser drift against real markup is a standing risk.
  `tests/fixtures/REPOINT.md` documents the exact capture command and what to verify; `tests/test_annas.py` runs the parser against
  `search_page_real.html` automatically once a capture is dropped in (skipped until then).
- The `annas` sign-in stores cookies in-process only; a restart signs in again, and there is no refresh or multi-mirror failover.
- Vectors live only inside sqlite-vec (no external index); there is no incremental re-embed scheduler (run `tools/reindex.py` manually after model changes).
- `eval_rag.py` needs a real embedder; with the hash embedder the numbers are meaningful only for regression checks, not quality claims.
- DjVu extraction shells out to `djvutxt`; without that binary the format is rejected with `UnsupportedFormat` rather than converted.
- The OCR confidence gate drops low-confidence tokens wholesale; badly scanned pages can produce empty OCR text instead of best-effort output.
- `INGEST_WINDOWS` is evaluated in UTC and does not wake a stopped host to ingest; the `ingest-override.json` grace file is
  advisory and only checked at the start of an ingest.
- The fetch guard still blocks only IPv4 loopback and link-local ranges (unchanged from the host skeleton); DNS-rebinding mitigation is incomplete.
- `rag` search result `url` fields use the internal `rag:md5:<hash>` scheme because local corpus documents have no canonical web URL.

## Hardening round (fix/rag-hardening)

- `lib/rag/rerank.py` — F1: `CrossEncoderReranker.score_many(query, texts)` issues one `rerank(query, texts)` call for the whole candidate batch (`rerank_texts` uses it); `.score` remains for single use. F2: `get_reranker()` returns a `LazyReranker` that resolves the cross-encoder on first score, caches it, and falls back to `LexicalReranker` on any failure; `RERANK_DISABLE=1` forces lexical without importing fastembed.
- `servers/rag_server.py` — F3: `fetch_page`, `search`, `rag_ask`, and `rag_index` are now `async def`; `fetch_url` is awaited directly (no nested `asyncio.run`) and sqlite/embedding work runs in `asyncio.to_thread`.
- `hub/app.py` — F4: `/api/health` no longer lets `**tiers` clobber reserved keys; the nested `tiers` object always wins and a tier colliding with `tiers`/`cache_ttl`/`tier_meta` is preserved under `tier_meta`.
- `lib/rag/db.py` — `chunks` gained a `page` column (schema + `ALTER TABLE` migration for existing stores) populated from `add_document(chunk_pages=...)`; `remove_document` was already deleting vectors (test added).
- `lib/rag/extract.py` — pdf/epub/txt/djvu extractors now return a `pages` list alongside the joined text so per-chunk page numbers are real, not inferred.
- `lib/rag/ingest.py` — chunks now span page breaks via `_chunk_with_pages` (a window may cross a boundary); each chunk records its *start* page and `chunk_pages` is passed through to the store.
- `lib/rag/retrieve.py` — hits carry `page`; `search(..., doc_ids=[...])` scopes every mode (vector SQL, bm25 SQL, and hybrid candidates) to the given md5s or doc_ids.
- `lib/rag/answer.py` — citations carry `doc_id` and `page`; `llm_complete` retries 429/5xx and transport errors (3 attempts, injectable sleep) and raises `LLMError`; a malformed LLM body degrades to a note instead of raising.
- `lib/rag/errors.py` — added `LLMError`.
- `lib/rag/gate.py` — midnight-wrapping windows (`22:00-02:00`) now parse and match correctly; `HUB_STATE/ingest-override.json` (`{"until": <epoch>, "reason": ...}`) temporarily opens ingestion and is ignored once expired.
- `lib/rag/tools/curate.py` — `import_docs` restores exported `pending_pins` (md5-keyed upsert), so a round-trip carries the pin queue.
- `lib/rag/tools/reindex.py` — reindex no longer inflates `corpus_daily` (today's counter is restored) and only records the new model identity when at least one document actually re-embedded; failed embedders leave the corpus untouched (resumable).
- `lib/rag/tools/golden_coverage.py` — per-query `status` (`covered` / `missing`) added under `per_query`.
- `lib/rag/tools/eval_rag.py` — `load_golden` accepts both `[...]` and `{"queries": [...]}` payloads.
- `tests/test_rag_audit.py` — Part 2 audit: schema/trigger/migration tests, `vec_chunks` cleanup on delete, RRF k=60 and 0.7 blend constants on the live path, `doc_ids` scoping per mode, no-context answer path, LLM retry/`LLMError`/malformed-body degradation, guard numbers, gate windows/override, reindex resumability + daily-counter neutrality, curate pending-pin round-trip, hand-computed nDCG/MRR fixture, golden-coverage statuses, and page-start chunk windows.
- `tests/test_rag_rerank.py` — F1/F2: `score_many` issues a single inference pass, `LazyReranker` defers model load and falls back to lexical, `RERANK_DISABLE=1` short-circuits.
- `tests/test_rag_server.py` — F3: async tool contract; an async tool calling `fetch_url` must not raise `RuntimeError`; embedder initialization is proven to happen off the event loop.
- `tests/test_host.py` — F4: tier named `tiers` survives at top level via `tier_meta`.
- `tests/test_annas.py` — parser parameterized over the synthesized fixture and `search_page_real.html` (auto-skips until a real capture is dropped in; see `tests/fixtures/REPOINT.md`).
- `tests/fixtures/REPOINT.md` — capture command and checklist for repointing the parser at real Anna's Archive markup.
- `tests/test_rag_rerank.py` — new: one-inference-pass batching, lazy fallback, `RERANK_DISABLE`, and lexical passthrough.
- `tests/test_rag_audit.py` — new: WAL + vec0 dims, FTS insert/update/delete trigger sync, vector removal on delete, RRF k=60 hand check, doc_ids scoping, guard baseline/force/stale-history + `ShrinkBlocked` numbers, gate windows/midnight wrap/override/expiry/eval lock, hand-computed nDCG/MRR/recall, resumable+idempotent+daily-neutral reindex.
- `tests/test_rag_server.py` — tools exercised through `asyncio.run`; new proof that an async tool awaiting `fetch_url` inside a running loop does not raise `RuntimeError`.
- `tests/test_rag_answer.py` — retry-then-succeed, give-up raises `LLMError`, empty-corpus path never calls the LLM, malformed-body degradation, citation `doc_id`/`page`.
- `tests/test_rag_retrieve.py` — `doc_ids` scoping for md5 and doc_id forms; RRF formula check on synthetic rank lists.
- `tests/test_rag_core.py` — midnight-wrap windows and override-file tests for the gate.
- `tests/test_rag_tools.py` — hand-computed metric math, curate pending-pin round-trip, per-query coverage statuses, reindex daily-count neutrality.
- `tests/test_dropin.py` — new: `literature`, `vulns`, and `localcode` stubs registered under those names load, answer `/api/search`, and show `state ok` in `/api/health` with zero host changes; hub/server source contains none of those names.
- `tests/test_host.py` — F4 collision test (a tier literally named `tiers`).
- `tests/test_annas.py` — parser tests parameterized over the synthesized fixture and `search_page_real.html` (skipped until a real capture exists).
- `tests/fixtures/REPOINT.md` — capture command and checklist for repointing the parser at real Anna's Archive markup.
