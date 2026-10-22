# sitejack

> **REA reverse-engineers apps. sitejack wears websites.**

A drop-in **skill for AI agents** that clones any website's *interface* — **byte-faithful, not a guess** — then gives your agent advanced commands over the clone: recon, secret-sweep, deploy, verify.

Screenshot-to-code tools *recreate* a UI from a picture and hope it looks similar. sitejack **mirrors the real frontend** — every chunk, font, stylesheet and route — and ships it as a live, served copy. Your agent (or you) can then extend it, restyle it, or study it.

```bash
python3 skill/sitejack.py recon  https://any.site          # stack, fonts, colors, endpoints
python3 skill/sitejack.py clone  https://any.site          # full byte-faithful mirror
python3 skill/sitejack.py scan   ./any.site-clone          # push-protection pre-flight
python3 skill/sitejack.py deploy ./any.site-clone my-repo  # GitHub repo + Pages, live in ~1 min
```

Python 3.8+ stdlib only. No dependencies. No headless browser. No build step.

## Why it's different

| | screenshot-to-code | source-scraper scripts | **sitejack** |
|---|---|---|---|
| Fidelity | approximated by an LLM | raw HTML dump | **byte-identical** (SHA-1 verified per file) |
| Asset graph | ✗ | partial | **closed graph**: JS → CSS → fonts → images → routes |
| Framework routes | ✗ | ✗ | routes become folders (`/pricing` → `pricing/index.html`) |
| Deploys itself | ✗ | ✗ | **GitHub Pages in one command** (auto `.nojekyll`, live check) |
| Secrets | ✗ | leaks them | **push-protection pre-flight scan** (10 token families, masked output) |
| Dead sites | ✗ | ✗ | `clone --wayback` mirrors from the **Wayback Machine** |
| Agent-native | prompt only | ✗ | `SKILL.md` + CLI contract, ready for Claude Code / Cursor / Base44 / MCP |

## Battle-tested, not a toy

sitejack was born in production: it mirrored a full **SvelteKit app with 203 files** (15 routes, 55 chunks, 22 nodes, 59 KaTeX fonts, PWA) and shipped it live:

- Live clone: https://mlk010173.github.io/skynetchat/
- Original: https://skynetchat.net

That run also caught a **Mapbox token embedded in a chunk** (blocked twice by GitHub Push Protection) — which is why `scan` exists and why `deploy` refuses to push dirty clones. Read the full story in [examples/case-study-skynetchat.md](examples/case-study-skynetchat.md).

The same engine now runs as **native agent tools inside JARVIS v1.3.7** (autonomous task engine: mirror → secret-sweep → human approval → publish). See [INTEGRATIONS.md](INTEGRATIONS.md).

## Install as an agent skill

sitejack is agent-native. Point your agent at this repo and it learns itself from [skill/SKILL.md](skill/SKILL.md):

```bash
git clone https://github.com/mlk010173/sitejack ~/.agents/skills/sitejack
```

Claude Code / Cursor / any agent with a skills folder: copy `skill/` in and say *"clone the interface of https://example.com and deploy it as example-clone"*. The skill file tells the agent the exact command sequence, the guardrails, and how to read the reports.

## Commands

| command | what it does |
|---|---|
| `recon <url>` | fingerprints the target: tech stack (SvelteKit, Next, WordPress, Shopify…), fonts, color palette, API endpoints in source, robots.txt |
| `clone <url>` | graph-closing crawler: pages, JS, CSS, fonts, images; routes→folders; caps and honest partial reports; `manifest.json` with SHA-1 per file |
| `clone <url> --wayback` | same, but pulls from web.archive.org — clone sites that are already down |
| `scan [dir]` | finds Mapbox/OpenAI/Google/GitHub/NVIDIA/Groq/Slack/AWS keys and private keys — masked, never printed — before GitHub blocks your push |
| `deploy <dir> <repo>` | creates the repo, `git push`, drops `.nojekyll` (Jekyll hides `_app`/`_next` folders — classic gotcha), activates Pages, polls until HTTP 200 |
| `verify <dir> <url>` | re-checks every file hash against the manifest: byte-faithful or it fails |

## What "interface clone" means (honest limits)

sitejack copies the **public frontend**: layout, components, styles, animations, fonts, assets, routes. It does **not** copy backends, databases, private data, or authenticated sessions — and it refuses to try (https-only, SSRF-guarded, no private hosts, no auth-walled content). API calls inside the clone still point to the original domain; the clone is a static interface twin.

## Ethics & legality

- Clone **public frontends you have the right to study or back up** — your own site, demos, design study, migration, archival.
- Don't republish someone else's brand or content as your own; design rights and copyright still apply.
- `scan` exists so you don't publish secrets by accident — the tool treats them as a hazard, not loot.
- Built-in guardrails: private-network blocked, http blocked, dangerous file types blocked, secrets masked.

## Roadmap

- [ ] MCP server (stdio) so any MCP client gets `sitejack.recon/clone/scan/deploy` as tools
- [ ] `watch <url>` — scheduled re-clone + diff report when a site changes
- [ ] `tokens <url>` — export design tokens (palette, type scale, spacing) as `tokens.json`
- [ ] `overlay` — inject a Ctrl+K command palette into the clone for demos
- [ ] Lighthouse-style post-deploy report (weights, waterfall)

Contributions welcome — keep it stdlib-only and honest.

## Em português (para o time BR)

sitejack é a skill de agente que **clona a interface de qualquer site de verdade** — byte a byte, não chute de screenshot — e ainda dá ao seu agente comandos avançados: `recon` (identifica o stack, fontes e cores), `clone` (espelho completo com grafo fechado de assets), `scan` (acha segredos antes do GitHub bloquear o push), `deploy` (repo + GitHub Pages no ar em um comando) e `verify` (prova criptográfica que o clone é idêntico). Site fora do ar? `--wayback` clona direto do Wayback Machine. Nasceu em produção clonando um app SvelteKit inteiro (203 arquivos, veja o case study) e já roda dentro do JARVIS como ferramentas nativas.

---

MIT © 2026 — made by an agent, for agents.
