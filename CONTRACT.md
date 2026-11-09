# Research Hub tier contract

This is a host skeleton, not a research tier. The production registry starts empty; `tests/stubs/stub_server.py` exists only for offline acceptance tests.

## Tier authoring

A tier is an MCP server using stdio. Add its implementation at `{{DEPLOY_DIR}}/servers/<name>_server.py`, then register it in `mcp_servers.json` using this exact shape:

```json
{"<name>": {"command": "uv", "args": ["run", "--with", "mcp[cli]<2,httpx", "python", "{{DEPLOY_DIR}}/servers/<name>_server.py"]}}
```

Do not add an `env` block or credentials to the registry. The host substitutes its deployment directory for `{{DEPLOY_DIR}}`, starts each configured process over MCP stdio, initializes the session, and discovers its tools at startup. Unknown extra registry fields are ignored.

The server must expose all five tools below. Each tool returns a JSON **string**; the displayed shapes describe the parsed JSON value.

| Tool | Input | JSON value in its returned string |
| --- | --- | --- |
| `search(query, limit=20)` | `query: str`, `limit: int = 20` | `{"results":[{"title":"…","author":"…","url":"…","tier":"…"}],"note":""}` |
| `fetch_page(url)` | `url: str` | `{"text":"…","bytes":0,"note":""}` |
| `pin_result(item)` | `item` object | Tier-defined JSON object describing the pin |
| `pinned()` | none | JSON array of pins |
| `unpin(id)` | `id: str` | Tier-defined JSON object describing the removal |

Search results must include string `title`, `author`, `url`, and `tier` fields. The host sets the exposed `tier` field to the registry name, regardless of the value returned by the server. The host calls `search` for fan-out; it discovers the other required tools but does not delegate its local pin API to them. `/api/fetch` is the host's separate HTTP(S) text fetcher.

## Host behavior

- `GET /api/search?query=…` calls all registered tiers concurrently. Each search call has a `HUB_TIER_TIMEOUT` deadline; a failure, timeout, or process exit becomes that tier's note and does not cancel the other results. The response is `{"results":[…],"notes":{"<tier>":{"state":"ok|degraded|skipped|absent","note":"…"}}}`.
- Results are merged in registry order. Duplicate identity is the lowercased title with non-alphanumeric characters removed, truncated to 60 characters; author is not part of identity. The first result wins and later tier names are listed in its `also_on` array.
- Search responses are cached in memory for 900 seconds by `(tier, normalized query)` in a least-recently-used cache capped at 500 entries. Query normalization strips outer whitespace, collapses internal whitespace, and case-folds.
- `GET /api/health` returns all registered names under `tiers`, each with its state, discovered tools, and note, plus `cache_ttl: 900`. Unknown registry fields do not affect loading.
- Tier states mean: **ok** — the process initialized and exposed all required tools; **degraded** — the process started but is missing required tools or a startup/search operation failed; **skipped** — its configuration is invalid or the command could not be started; **absent** — a configured absolute Python server path does not exist.
- `GET /api/fetch?url=…` accepts only HTTP(S), allows text content types, removes script/style contents from HTML, caps the body at 500 KiB, and applies a 20-second total timeout. Loopback IPv4 (`127.0.0.0/8`) and IPv4 link-local (`169.254.0.0/16`) destinations are refused unless `internal=1` is supplied.
- `POST /api/pin` and `GET /api/pins` operate on the host's SQLite pin store. `DELETE /api/pin/{id}` removes a pin. `expires_at: null` or omission makes a pin permanent; expired pins are swept every 15 minutes. At most 500 unexpired pins are accepted.
- `GET /api/watch` lists saved queries and `POST /api/watch` stores one. Watches do not run automatically.
- `/` serves the single vanilla-JS file `hub/index.html`. Its three panes are Literature, Vulnerabilities, and Local code; tiers are assigned by name heuristics. Unmatched tiers appear in Literature unless the optional fourth pane is enabled.

## Registering credentials

Pass tier-specific credentials through the process environment, never through `mcp_servers.json`. For a tier named `literature`, set variables such as `HUB_TIER_LITERATURE__API_KEY`; the matching child receives `API_KEY`. Hyphens in tier names are treated as underscores in this prefix. A tier receives only variables with its own prefix. The host itself is local-only and does not require credentials.

## Host assumptions

- **Deployment directory:** this copy is at `/home/workspace/research-hub`. At runtime `DEPLOY_DIR` is derived from the installed `hub` package location; `mcp_servers.json` is next to that directory. The process must be able to read the registry and tier scripts.
- **Registry file:** defaults to `<DEPLOY_DIR>/mcp_servers.json` (currently `{}`). `HUB_MCP_SERVERS` optionally overrides it with another JSON file path.
- **State directory:** `HUB_STATE` optionally overrides it; default is `~/.local/share/intel-hub`, expanded for the account running the host. SQLite is stored at `HUB_STATE/hub.sqlite3`.
- **Python:** Python 3.11 or newer with the `pyproject.toml` dependencies installed. MCP must be 1.x; the host exits with status 2 and an explanatory message for MCP 2.x or later.
- **Listener:** `HUB_PORT` optionally selects the port; default `8471`. The host binds only to `127.0.0.1`. It does not start any other listener. Start it from this directory with `python -m hub`.
- **Search deadline:** `HUB_TIER_TIMEOUT` is the per-tier search timeout in seconds; default `12`. Startup discovery has a minimum five-second timeout per tier.
- **Dashboard layout:** `HUB_FOURTH_PANE=1` enables the catch-all fourth pane; any other value leaves the three-pane layout.
- **Tier environment:** optional `HUB_TIER_<NAME>__<KEY>` variables are passed only to that tier process. Secrets must be supplied by the operator's environment, not committed files.
- **Self-check:** `./scripts/selfcheck.sh` runs imports, Ruff, pytest, the listener check, and the registry secret scan. It uses `ss -ltn` when available; if `ss` is absent, it reads the Linux TCP tables under `/proc` instead.

## Known gaps

- No production tiers, scheduler, remote authentication, persistent result cache, or tier-management UI are included. The test stub is not registered by default.
- The host pin API is centralized in SQLite; tier-level pin tools are required by the interface but are not invoked by the host.
- The fetch guard blocks the specified IPv4 loopback and link-local ranges, not every private, multicast, or reserved network. DNS is checked before the HTTP client resolves the host again, so a hostile DNS rebinding target is not fully mitigated.
- Tier-to-pane placement is name-based. An unmatched tier goes to Literature when the optional fourth pane is disabled.
- SQLite stores pins and saved queries locally without encryption. Keep `HUB_STATE` protected by the operating system account permissions.
