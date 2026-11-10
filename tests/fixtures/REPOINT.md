# Repointing the Anna's Archive parser to real markup

No live search page could be captured while building this repo: Anna's Archive
blocks cloud/datacenter IPs, so `search_page.html` is a synthesized fixture that
mimics the documented card layout (`/md5/<32hex>` anchor as title, author line,
`language · FORMAT · size · year` details line). Until a real page is captured,
the parser is verified against the synthesized markup only.

## Capture command (run from a residential IP or VPN exit that the mirror serves)

```bash
curl -sS -L -A "Mozilla/5.0 (X11; Linux x86_64) Firefox/128.0" \
  --cookie-jar /tmp/annas.cookies --cookie /tmp/annas.cookies \
  "https://annas-archive.gd/search?q=information+theory" \
  -o tests/fixtures/search_page_real.html
```

If the mirror answers with a Cloudflare challenge instead of search results, the
file will contain "Just a moment" or an `cf-challenge` script; that capture is
NOT usable — retry from a different exit, or export the page HTML from a normal
browser session (View Source, save as `search_page_real.html`).

## What to check after capture

1. `grep -c 'href="/md5/[0-9a-f]\{32\}"' tests/fixtures/search_page_real.html`
   — confirms the anchor shape the parser keys on still exists (Anna's Archive
   has historically used `/md5/<hash>` and `/scidb/<hash>` variants).
2. `pytest tests/test_annas.py -q` — the parser tests are parameterized over
   both fixtures; the real-fixture cases skip until this file exists and then
   run against it. If they fail, the card layout changed: update
   `lib/annas.py::parse_results` to the new anchor/metadata structure and keep
   both fixtures passing (do not delete the synthesized one).
3. Confirm the real page's card order matches what the site shows in a browser,
   so the `limit` semantics stay honest.

Once `search_page_real.html` passes, remove the "parser verified against
synthesized markup only" line from `GUARDRAILS.md` → Known gaps.
