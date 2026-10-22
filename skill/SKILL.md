# sitejack — agent skill

You now know how to clone any website's public interface, byte-faithfully, and deploy it as a live copy on GitHub Pages. Follow this file exactly.

## Tool

Single-file CLI at `skill/sitejack.py` (Python 3.8+ stdlib only). Run with `python3 skill/sitejack.py <command>`.

## Command contract

| command | use it when | on failure |
|---|---|---|
| `recon <url>` | the user names a site they want studied or cloned | report the HTTP status honestly; do not guess the stack |
| `clone <url>` | the user wants the interface copied; mirror lands in `./<host>-clone/` with `manifest.json` | a partial report in the manifest is normal for huge sites — say how deep it went |
| `clone <url> --wayback` | the site is down or returns errors | wayback mirrors are best-effort; say so |
| `scan <dir>` | ALWAYS between clone and deploy — non-negotiable | if it exits with code 2, STOP: there are secrets. Show the masked findings, propose removal, never deploy |
| `deploy <dir> <repo>` | the user asks to publish; requires `GITHUB_TOKEN` env (repo scope) | if Pages build hasn't finished, say it is building — never claim live without HTTP 200 |
| `verify <dir> <url>` | the user doubts the copy, or before claiming "perfect clone" | exit code 2 means hash mismatch — report exactly which files |

## The canonical run

When a user says "clone this site and put it online":

1. `recon <url>` — tell them the stack, fonts, palette, and roughly how many assets.
2. `clone <url>`.
3. `scan` the clone dir. If secrets: STOP and report.
4. `deploy <dir> <repo-name>` — picks a repo name close to the brand; asks the user only if the name matters.
5. Report the live URL and the repo URL. Offer `verify` as proof.

## Guardrails (hard rules)

- Public frontends only. https-only. Private/internal hosts are blocked by the tool — never work around it.
- Never try to clone authenticated content, paid content, or anything behind a login.
- Never print a secret the scan finds — it prints masked; keep it masked in your replies.
- Never claim byte-fidelity without running `verify`.
- Clones are static: API calls still point to the original domain. Say this when the user expects functionality, not just the interface.
- If the user seems to want to impersonate someone's brand/site, ask what the clone is for and suggest legal alternatives (backup, study, redesign, demo).

## Reading the outputs

- `manifest.json` — every saved file with size and SHA-1; `skipped` explains every absence; `partial: true` means the cap hit before the graph closed.
- `scan` output — file, secret family (Mapbox, OpenAI…), masked fragment. This mirrors what GitHub Push Protection blocks, so a clean scan ≈ a push that goes through.
- `deploy` — prints `LIVE: <url>` only after an HTTP 200 check on the Pages URL.

## Known gotchas the tool already handles (don't reintroduce them)

- GitHub Pages runs Jekyll, which silently ignores folders starting with `_` (like SvelteKit's `_app` or Next's `_next`) — `deploy` writes `.nojekyll` for you.
- Routes without extensions (`/pricing`) must land in `pricing/index.html`, or they 404 on Pages.
- Absolute URLs in the source must stay absolute (they point at the original); only same-origin paths become clone files.
