# Case study: cloning a full SvelteKit app in production

**Target:** https://skynetchat.net — "Chat de IA em português", a SvelteKit app with SSR, PWA, a checkout, an affiliate system and a map.

**Result (live):** https://mlk010173.github.io/skynetchat/ — 203 files mirrored and served by GitHub Pages.

## What was mirrored

- 15 rendered routes (chat, login, sign-up, checkout, affiliate panel, monetize, terms, about, PWA, recovery, dev-panel, and more), each landing in its own `route/index.html` folder so Pages serves them
- 55 SvelteKit JS chunks, 22 nodes, both entry points
- Full compiled CSS, 59 KaTeX font files (woff2/ttf)
- Images, favicons, PWA icons, web manifest, robots.txt

## What bit us (and what the tool now bakes in)

1. **GitHub Push Protection blocked the push — twice.** The site embeds a public Mapbox frontend token inside `_app/immutable/nodes/16.DrcJp8ja.js`. GitHub flags it even though it's a public-by-design frontend token. We neutralized it in the mirror and squashed the history into one clean commit. → This is why sitejack ships `scan` as a required pre-flight step.
2. **GitHub Pages runs Jekyll**, which silently ignores folders starting with `_`. The whole `_app` tree 404'd until we dropped a `.nojekyll` at the repo root. → `deploy` writes it automatically.
3. **Routes are not files.** `/voz` isn't a file, it's a route that must become `voz/index.html` or it won't resolve on Pages. → `clone` does the mapping.
4. **Refs have three shapes** (`/absolute`, `./relative`, `../up`), each resolving to a different place. Getting this wrong is how most scrapers miss chunk-loader chains and font sets. → the crawler resolves all three and closes the asset graph.

## Honest limits observed

The clone is a static interface twin: visuals, components, animations and navigation all work; `/api/*` calls still target the original domain, so chat/login in the *clone* are non-functional by design. The map's neutralized token means the map component doesn't render in the mirror (it renders fine on the original site).

## Same engine, other form factor

The mirror logic was then productized as **native agent tools inside JARVIS v1.3.7** (an autonomous task engine): `site_espelhar` (mirror), `site_segredos` (secret sweep), `site_publicar` (repo + Pages, gated behind human approval). The task engine runs mirror → sweep → approval → publish autonomously. sitejack is the standalone, dependency-free version of the same know-how.
