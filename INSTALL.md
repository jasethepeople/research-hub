# Installing research-hub

Research Hub is a **single local process** (the *host*) that talks to small helper
programs called **tiers**. One process, one port (`127.0.0.1:8471`), everything
else is started on demand and talks over standard input/output — there are no
daemons, sidecars, or extra ports to babysit.

---

## 1. What you need before you start

| Requirement | Why | Check with |
|---|---|---|
| Python **3.11 or newer** | runs the host and the tests | `python3 --version` |
| [uv](https://docs.astral.sh/uv/) | launches each tier in its own isolated environment; also what downloads the RAG extras | `uv --version` |
| `git` | to clone the repository | `git --version` |
| (optional) `tesseract-ocr` | only needed if you want scanned-PDF OCR | `tesseract --version` |
| (optional) `djvutxt` | only needed for DjVu files | `djvutxt --version` |

Everything else is installed by pip. Nothing is downloaded at runtime except:

- the embedding model the **first** time you run a RAG search (cached by fastembed
  in its own model directory — set `UV_CACHE_DIR`/fastembed's cache somewhere with
  room if your home is small),
- documents you explicitly ingest or download.

If you have no network at all, the base install still works; the RAG tier simply
reports itself as "unavailable" instead of failing.

## 2. Get the code

```bash
git clone https://github.com/jasethepeople/research-hub
cd research-hub
```

## 3. Create the virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -U pip
```

## 4. Install the packages

**Base install (host + Anna's Archive tier + tests):**

```bash
pip install -e '.[test]'
```

**Full install (adds local RAG: PDF/EPUB extraction, embeddings, vector search):**

```bash
pip install -e '.[test,rag]'
```

The base install is deliberately light. Without the `rag` extra the RAG tier
still loads and answers tools with a clean `unavailable` note — nothing crashes.

**Optional system packages** (install with your OS package manager, e.g.
`sudo apt install tesseract-ocr`):

- `tesseract-ocr` — enables OCR for scanned PDFs (300 dpi, confidence-gated).
- `djvutxt` (part of DjVuLibre) — enables DjVu text extraction.

## 5. Pick a state directory

All state (pins, the RAG database, downloaded documents) lives under **one**
folder pointed to by `HUB_STATE`. Choose somewhere with disk space:

```bash
mkdir -p ~/research-hub-state
export HUB_STATE="$HOME/research-hub-state"
```

Put that `export` line in your `~/.bashrc` (or shell equivalent) so it survives
reboots. The directory is created automatically if it doesn't exist. Nothing is
ever written outside `HUB_STATE` — the code refuses to touch `~/code` or any
other home directory.

## 6. Verify the install

```bash
./scripts/selfcheck.sh
```

Expected output ends with something like:

```
imports: ok
All checks passed!
80 passed, ...          (pytest — exact count grows over time; "passed" is what matters)
mcp_servers.json secret scan: 0 matches
```

The script also prints the listening sockets and stops with an error if any
secret-looking string appears in the registry. Only `127.0.0.1:8471` should ever
appear as a hub-owned listener.

Run the offline test suite directly any time with:

```bash
pytest -q
```

It is fully offline: no network, no model downloads (RAG tests use
deterministic hash embeddings), and OCR tests skip themselves when tesseract is
absent.

## 7. Environment variables reference (all optional)

| Variable | Default | Purpose |
|---|---|---|
| `HUB_STATE` | platform state dir | **Set this one.** Where all data lives. |
| `HUB_PORT` | `8471` | Port for the dashboard/API. Always bound to `127.0.0.1`. |
| `HUB_TIER_TIMEOUT` | `12` | Seconds each tier gets per search call. |
| `HUB_MCP_SERVERS` | `<repo>/mcp_servers.json` | Registry file listing the tiers. |
| `HUB_FOURTH_PANE` | `0` | Set to `1` to unlock the optional fourth dashboard pane. |
| `ANNAS_KEY` | *(empty)* | Anna's Archive account key (never commit it). |
| `ANNAS_MIRROR` | `https://annas-archive.gd` | Mirror to search. |
| `ANNAS_STORE` | `<HUB_STATE>/annas` | Where `download` saves files. |
| `LLM_BASE_URL` | *(empty)* | OpenAI-compatible endpoint for `rag_ask` answers. |
| `LLM_MODEL` | *(empty)* | Model name sent to that endpoint. |
| `LLM_API_KEY` | *(empty)* | Bearer key for that endpoint. |
| `INGEST_WINDOWS` | *(empty)* | e.g. `"02:00-05:00"` — ingest only inside the window(s) (UTC). |
| `RERANK_DISABLE` | *(empty)* | `1` forces the lexical reranker (no cross-encoder download). |

Per-tier settings use the pattern `HUB_TIER_<NAME>__<VAR>`, e.g.
`HUB_TIER_ANNAS__ANNAS_KEY` sets `ANNAS_KEY` for the `annas` tier only.

**Secrets:** never put keys in any committed file. Pass them through the
environment (shell profile, `.env` tooling, or the host's secret store). The
selfcheck fails if a key-shaped string appears in `mcp_servers.json`.

## 8. Troubleshooting the install

- **`uv: command not found`** — tiers cannot start without uv. Install it:
  `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- **First RAG search hangs a while** — that's the one-time embedding-model
  download. Subsequent calls are fast. Set `RERANK_DISABLE=1` if you also want to
  skip the cross-encoder model.
- **`RagUnavailable` notes from the rag tier** — the `[rag]` extra isn't
  installed in the environment the tier runs in. Reinstall with
  `pip install -e '.[rag]'`; the tier is launched through uv, which creates an
  isolated environment, so `mcp_servers.json` already lists the needed packages.
- **Port 8471 already in use** — set `HUB_PORT` to another port; the invariant
  "one listener" is about one *hub*, not one magic number.

---

Next: read **USAGE.md** for day-to-day operation.
