# research-hub

A local, tier-ready research hub host. One FastAPI process on `127.0.0.1:8471`
fans queries out to MCP-over-stdio tiers, merges and dedupes their results,
pins and watches queries in SQLite, and serves a three-pane dashboard.

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[test]'
python -m hub            # starts the host on 127.0.0.1:8471
```

- Dashboard: `http://127.0.0.1:8471/`
- Search: `/api/search?query=...`
- Health: `/api/health` (tiers listed under `tiers` and mirrored at top level)
- Fetch: `/api/fetch?url=...` (http(s), text, 500 KiB, 20 s; loopback needs `internal=1`)

## Shipped tiers

| Tier | Script | Extra tools | Notes |
| --- | --- | --- | --- |
| `annas` | `servers/annas_server.py` | `download(md5)` | Anna's Archive search via `ANNAS_KEY`/`ANNAS_MIRROR`; 250 MiB downloads to `ANNAS_STORE`. |
| `rag` | `servers/rag_server.py` | `rag_ask`, `rag_index` | Local sqlite-vec/FTS5 corpus at `HUB_STATE/rag.sqlite3`; needs the `[rag]` extra; answers cite only retrieved passages. |

Register tiers in `mcp_servers.json`; secrets go through the environment
(`HUB_TIER_<NAME>__<KEY>`), never the registry. See `CONTRACT.md` for the full
tier contract and `GUARDRAILS.md` for the invariant map.

## Development

```bash
pip install -e '.[test,rag]'
./scripts/selfcheck.sh   # imports, ruff, pytest, listener check, secret scan
pytest -q                # offline; hash-embedded vectors, no model downloads
ruff check hub servers lib tests
```
