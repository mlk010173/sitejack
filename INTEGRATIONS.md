# sitejack inside JARVIS

The mirror engine in this repo is not a lab project: the same logic runs as **native tools in JARVIS v1.3.7**, an autonomous task engine (https://github.com/mlk010173/jarvis).

JARVIS agents run the whole sitejack loop as one task:

1. `site_espelhar` — mirrors the public frontend (SSRF-guarded, per-round caps, resumes across runs)
2. `site_segredos` — push-protection sweep over the mirror
3. `site_publicar` — creates the GitHub repo, pushes with `.nojekyll`, activates Pages — gated behind **human approval**, and refuses to publish files that contain secrets

Example autonomous task: *"Espelhe o site X, verifique segredos e publique no repo Y"* — the engine plans the three steps itself, stops for approval before publishing, and returns the live URL as evidence.

sitejack (this repo) is the standalone, dependency-free, human-usable version of that engine — same guardrails, same honesty rules.
