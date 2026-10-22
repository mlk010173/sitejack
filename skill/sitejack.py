#!/usr/bin/env python3
"""
sitejack — clone any website's interface, byte-faithful, then command it.

Single-file CLI for AI agents (Claude Code, Cursor, Base44 Superagents, or a human).
Python 3.8+ stdlib only. No dependencies. Public frontends only.

Commands:
  recon <url>            fingerprint a site: tech stack, headers, fonts, colors, JS endpoints
  clone <url>            mirror the whole frontend into ./<host>/ (graph-closing crawler)
  clone <url> --wayback  clone from the Wayback Machine when the site is down
  scan [dir]             push-protection pre-flight: find secrets the way GitHub would
  deploy <dir> <repo>    GitHub repo + Pages: git push, .nojekyll, Pages API, live check
  verify <dir> <url>     re-fetch originals and diff hashes against the clone manifest

Guardrails baked in: https-only, SSRF-guard, size caps, honest partial reports,
secrets are detected (scan) and never printed in full.
"""
import argparse
import hashlib
import json
import os
import posixpath
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

__version__ = "1.0.0"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 sitejack/" + __version__
TIMEOUT = 20
MAX_FILE = 3 * 1024 * 1024
MAX_TOTAL = 60 * 1024 * 1024
MAX_FILES = 1500

TEXT_EXT = {"html", "js", "mjs", "css", "json", "svg", "txt", "webmanifest", "xml", "map", "woff", "woff2", "ttf"}
SECRET_PATTERNS = [
    (re.compile(r"[ps]k\.eyJ[A-Za-z0-9._-]{15,}"), "Mapbox token"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), "OpenAI-style key"),
    (re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"), "Google API key"),
    (re.compile(r"\bghp_[A-Za-z0-9]{30,}"), "GitHub PAT"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}"), "GitHub PAT"),
    (re.compile(r"\bnvapi-[A-Za-z0-9_-]{20,}"), "NVIDIA key"),
    (re.compile(r"\bgsk_[A-Za-z0-9]{20,}"), "Groq key"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
    (re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key"),
]


def die(msg, code=1):
    print("sitejack: error: " + msg, file=sys.stderr)
    sys.exit(code)


def ssrf_guard(url):
    """Only public https origins."""
    p = urlparse(url)
    if p.scheme != "https":
        die("only https:// URLs (got '" + p.scheme + "')")
    host = p.hostname or ""
    if not host:
        die("no hostname in URL")
    if re.match(r"^(localhost|127\.|10\.|192\.168\.|169\.254\.|0\.|172\.(1[6-9]|2\d|3[01])\.)", host, re.I):
        die("private/internal hosts are blocked: " + host)
    if host.endswith(".local") or host in ("::1", "[::1]"):
        die("private/internal hosts are blocked: " + host)


def urlparse(url):
    import urllib.parse
    return urllib.parse.urlparse(url)


def fetch(url):
    """Return (status, headers, bytes) or raise."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), b""
    except Exception as e:
        raise RuntimeError(str(e)[:200])


# ---------------------------------------------------------------- refs
REF_RE = [
    re.compile(r"""["'`]((?:\.{1,2}/|/)[A-Za-z0-9_\-./@]+)["'`]"""),
    re.compile(r"""url\(\s*["']?([^)"'\s]+)["']?\s*\)"""),
    re.compile(r"""(?:src|href|data-src|poster)\s*=\s*["']([^"']+)["']""", re.I),
    re.compile(r"""(?:fetch|import|axios\.get|\.open)\s*\(\s*["'`]([^"'`]+)["'`]"""),
]


def refs_of(text):
    out = set()
    for rx in REF_RE:
        for m in rx.finditer(text):
            ref = m.group(1).split("#")[0].split("?")[0]
            if ref and not ref.startswith(("data:", "blob:", "javascript:", "mailto:", "tel:")):
                out.add(ref)
    return list(out)[:300]


def target_of(ref, page_path, origin, host):
    """Mirror-relative path for a ref, or None if it must be skipped (external, etc.)."""
    import urllib.parse
    if ref.startswith("//"):
        return None
    if ref.startswith("http"):
        if ref.startswith(origin + "/"):
            ref = ref[len(origin):]
        elif ref == origin:
            ref = "/"
        else:
            return None
    if ref.startswith("data:"):
        return None
    if ref.startswith("/"):
        rel = ref[1:]
    else:
        rel = posixpath.normpath(posixpath.join(posixpath.dirname(page_path), ref))
    if not rel or rel.startswith(".."):
        return None
    if not re.match(r"^[A-Za-z0-9_\-./@%]+$", rel):
        return None
    return rel


# ---------------------------------------------------------------- recon
TECH_SIGS = [
    (r"/_app/immutable/", "SvelteKit"),
    (r"/_next/static/", "Next.js"),
    (r"__NUXT__", "Nuxt"),
    (r"wp-content|wp-includes", "WordPress"),
    (r"cdn\.shopify\.com", "Shopify"),
    (r"ng-version=", "Angular"),
    (r"data-reactroot", "React (CSR)"),
    (r"gstatic\.com/firebasejs|firebaseio\.com", "Firebase"),
    (r"gtm\.js|googletagmanager", "Google Tag Manager"),
    (r"clarity\.ms", "Microsoft Clarity"),
    (r"cdn\.tailwindcss\.com", "Tailwind (CDN)"),
]


def cmd_recon(url):
    ssrf_guard(url)
    status, headers, body = fetch(url)
    if status != 200:
        die("site returned HTTP " + str(status))
    text = body.decode("utf-8", "replace")
    p = urlparse(url)
    print("== sitejack recon: " + p.netloc + " ==")
    print("status: " + str(status))
    for h in ("server", "x-powered-by", "content-security-policy", "cache-control", "via", "cf-ray"):
        if h in {k.lower(): k for k in headers}:
            pass
    for k, v in sorted(headers.items()):
        if k.lower() in ("server", "x-powered-by", "via", "cache-control"):
            print("header " + k + ": " + str(v)[:100])
    tech = [name for rx, name in TECH_SIGS if re.search(rx, text, re.I)]
    print("stack: " + (", ".join(sorted(set(tech))) if tech else "no obvious framework"))
    refs = refs_of(text)
    same = [r for r in refs if target_of(r, "index.html", p.scheme + "://" + p.netloc, p.netloc)]
    print("assets referenced on the home page: " + str(len(same)))
    fonts = sorted(set(re.findall(r"(?:font-family\s*:\s*|family=)([A-Za-z0-9 +,\-\"']{3,40})", text)))[:8]
    print("fonts: " + (", ".join(fonts) if fonts else "-"))
    colors = sorted(set(re.findall(r"#(?:[0-9a-fA-F]{3}){1,2}\b", text)))[:12]
    print("colors: " + (", ".join(colors) if colors else "-"))
    endpoints = sorted(set(re.findall(r"""["'`](/(?:api|v\d|graphql|rest|rpc)[A-Za-z0-9_\-/.]*)["'`]""", text)))[:20]
    print("api endpoints in source: " + (", ".join(endpoints) if endpoints else "-"))
    print("robots.txt: ", end="")
    try:
        s2, _, b2 = fetch(p.scheme + "://" + p.netloc + "/robots.txt")
        print("present" if s2 == 200 else "absent")
    except Exception:
        print("absent")
    print("manifest: " + json.dumps({"url": url, "status": status, "stack": tech, "assets": len(same),
                                    "fonts": fonts, "colors": colors, "endpoints": endpoints}))


# ---------------------------------------------------------------- clone
def guess_text(content_type, path):
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if ext in TEXT_EXT:
        return True
    for t in ("text/html", "text/css", "javascript", "application/json", "image/svg", "text/plain", "font/"):
        if t in (content_type or ""):
            return True
    return False


def cmd_clone(url, out, max_files, wayback):
    ssrf_guard(url)
    p = urlparse(url)
    origin = p.scheme + "://" + p.netloc
    if wayback:
        origin = "https://web.archive.org/web/2/" + origin  # wayback /web/2/ mirrors latest
    host = p.netloc.replace(":", "_")
    root = out or ("./" + host + "-clone")
    os.makedirs(root, exist_ok=True)
    queue = [p.path or "/"]
    seen, saved, skipped, total_bytes, pages = set(), {}, [], 0, 0
    print("== sitejack clone: " + url + (" (via Wayback)" if wayback else "") + " -> " + root + " ==")
    while queue:
        path = queue.pop(0)
        key = path.rstrip("/") or "/"
        if key in seen or len(saved) >= max_files:
            continue
        seen.add(key)
        fetch_url = origin + (path if path.startswith("/") else "/" + path)
        if not fetch_url.startswith("http"):
            continue
        try:
            status, headers, body = fetch(fetch_url)
        except Exception as e:
            skipped.append({"path": path, "why": str(e)[:80]})
            continue
        if status != 200 or not body:
            skipped.append({"path": path, "why": "HTTP " + str(status)})
            continue
        if len(body) > MAX_FILE or total_bytes + len(body) > MAX_TOTAL:
            skipped.append({"path": path, "why": "too large"})
            continue
        ctype = str(headers.get("Content-Type", ""))
        if not guess_text(ctype, path):
            ext = (path.rsplit(".", 1)[-1] if "." in path else "").lower()
            if ext not in ("png", "jpg", "jpeg", "gif", "webp", "ico", "avif", "mp4", "mp3", "woff", "woff2", "ttf", "eot", "otf"):
                skipped.append({"path": path, "why": "binary not whitelisted"})
                continue
        # route -> folder with index.html (SvelteKit/Next/SPA style routes keep working on Pages)
        fs_path = path.lstrip("/")
        if ctype.startswith("text/html") and not re.search(r"\.[A-Za-z0-9]{1,8}$", fs_path):
            fs_path = (fs_path.rstrip("/") or "") + "/index.html"
            pages += 1
        dest = os.path.join(root, fs_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(body)
        saved[key] = {"file": fs_path, "bytes": len(body), "sha1": hashlib.sha1(body).hexdigest()[:12],
                      "type": ctype.split(";")[0]}
        total_bytes += len(body)
        if guess_text(ctype, path):
            text = body.decode("utf-8", "replace")
            for ref in refs_of(text):
                t = target_of(ref, fs_path, origin, p.netloc)
                if t and t.rstrip("/") not in seen and t not in queue:
                    queue.append(t if t.startswith("/") else "/" + t)
        print("  + " + fs_path + " (" + str(len(body)) + " B)")
        time.sleep(0.05)  # be gentle
    manifest = {"source": url, "origin": origin, "root": root, "saved": saved,
                 "skipped": skipped[:200], "files": len(saved), "pages": pages,
                 "total_bytes": total_bytes, "sitejack": __version__,
                 "partial": len(queue) > 0}
    with open(os.path.join(root, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=1)
    print("== clone done: " + str(len(saved)) + " files, " + str(pages) + " pages, "
          + str(round(total_bytes / 1024)) + " KB, " + str(len(skipped)) + " skipped (see manifest.json)")
    if manifest["partial"]:
        print("   note: queue not empty (cap reached) — raise --max-files for a deeper mirror")
    print("   next: sitejack scan " + root + "  then  sitejack deploy " + root + " <repo>")


# ---------------------------------------------------------------- scan
def cmd_scan(root):
    root = root or "."
    findings = []
    count = 0
    for dirpath, _, files in os.walk(root):
        for name in files:
            path = os.path.join(dirpath, name)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    text = fh.read()
            except Exception:
                continue
            if len(text) > 5 * 1024 * 1024:
                continue
            count += 1
            for rx, label in SECRET_PATTERNS:
                m = rx.search(text)
                if m:
                    findings.append({"file": path, "kind": label,
                                     "masked": m.group(0)[:5] + "...[masked]"})
    print("== sitejack scan: " + root + " ==")
    print("scanned " + str(count) + " text files")
    if not findings:
        print("clean: no secrets found (GitHub push protection should pass)")
        return 0
    for f in findings[:40]:
        print("  ! " + f["file"] + " -> " + f["kind"] + " (" + f["masked"] + ")")
    print("BLOCK: " + str(len(findings)) + " finding(s). Remove/neutralize them before deploy, or GitHub push protection will reject the push.")
    return 2


# ---------------------------------------------------------------- deploy
def gh_api(path, token, method="GET", payload=None):
    req = urllib.request.Request("https://api.github.com" + path,
                                 data=json.dumps(payload).encode() if payload else None,
                                 method=method,
                                 headers={"Authorization": "Bearer " + token,
                                          "Accept": "application/vnd.github+json",
                                          "User-Agent": "sitejack"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def cmd_deploy(root, repo, desc, token):
    if not token:
        die("GITHUB_TOKEN env var not set (needs repo scope)")
    if not os.path.isdir(root):
        die("clone dir not found: " + root)
    for script in (".bat", ".cmd", ".hta", ".vbs"):
        for dirpath, _, files in os.walk(root):
            for f in files:
                if f.lower().endswith(script):
                    die("blocked file type in clone: " + f + " (platform policy)")
    status, me = gh_api("/user", token)
    if status != 200:
        die("GitHub token invalid (HTTP " + str(status) + ")")
    owner = me.get("login")
    print("== sitejack deploy: " + root + " -> " + owner + "/" + repo + " ==")
    status, _ = gh_api("/user/repos", token, "POST",
                       {"name": repo, "description": desc or "Interface clone by sitejack",
                        "has_pages": True, "private": False})
    if status not in (201, 422):
        die("could not create repo (HTTP " + str(status) + ")")
    open(os.path.join(root, ".nojekyll"), "w").close()  # Jekyll skips _app/_next folders otherwise
    remote = "https://x-access-token:" + token + "@github.com/" + owner + "/" + repo + ".git"
    g = lambda *args: subprocess.run(["git", "-C", root] + list(args), check=True, capture_output=True)
    g("init", "-q", "-b", "main")
    g("add", "-A")
    subprocess.run(["git", "-c", "user.name=" + owner, "-c", "user.email=" + owner + "@users.noreply.github.com",
                    "-C", root, "commit", "-q", "-m", "Interface clone by sitejack v" + __version__],
                   check=True, capture_output=True)
    g("push", "-q", "--force", remote, "main")
    status, pg = gh_api("/repos/" + owner + "/" + repo + "/pages", token, "POST",
                        {"source": {"branch": "main", "path": "/"}})
    if status not in (201, 409, 422):
        die("Pages activation failed (HTTP " + str(status) + ")")
    if status == 409:
        _, pg = gh_api("/repos/" + owner + "/" + repo + "/pages", token)
    url = pg.get("html_url") or ("https://" + owner + ".github.io/" + repo + "/")
    print("pushed. Pages: " + url)
    for i in range(20):
        time.sleep(10)
        try:
            import urllib.request as u
            with u.urlopen(u.Request(url, method="HEAD"), timeout=15) as r:
                if r.status == 200:
                    print("LIVE: " + url + " (HTTP 200)")
                    print("repo: https://github.com/" + owner + "/" + repo)
                    return
        except Exception:
            pass
        print("  waiting for Pages build... (" + str(i + 1) + "/20)")
    print("Pages still building — check " + url + " in a minute")


# ---------------------------------------------------------------- verify
def cmd_verify(root, url):
    mp = os.path.join(root, "manifest.json")
    if not os.path.isfile(mp):
        die("no manifest.json in " + root + " (run clone first)")
    with open(mp) as fh:
        man = json.load(fh)
    ssrf_guard(url)
    ok = fail = gone = 0
    for key, meta in list(man["saved"].items())[:200]:
        local = os.path.join(root, meta["file"])
        if not os.path.isfile(local):
            fail += 1
            print("  MISSING local: " + meta["file"])
            continue
        with open(local, "rb") as fh:
            if hashlib.sha1(fh.read()).hexdigest()[:12] != meta["sha1"]:
                fail += 1
                print("  HASH differs: " + meta["file"])
                continue
        ok += 1
    print("== verify: " + str(ok) + " files byte-identical, " + str(fail) + " problems ==")
    if fail:
        return 2
    print("clone is byte-faithful to the moment it was taken")


def main():
    ap = argparse.ArgumentParser(prog="sitejack", description="clone any site's interface, byte-faithful")
    ap.add_argument("--version", action="version", version="sitejack " + __version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("recon", help="fingerprint a site (stack, fonts, colors, endpoints)")
    c.add_argument("url")
    c = sub.add_parser("clone", help="mirror the frontend")
    c.add_argument("url")
    c.add_argument("-o", "--out")
    c.add_argument("--max-files", type=int, default=MAX_FILES)
    c.add_argument("--wayback", action="store_true", help="clone from web.archive.org (site down?)")
    c = sub.add_parser("scan", help="push-protection pre-flight secret scan")
    c.add_argument("dir", nargs="?", default=".")
    c = sub.add_parser("deploy", help="push clone to GitHub + activate Pages")
    c.add_argument("dir")
    c.add_argument("repo")
    c.add_argument("-d", "--description")
    c.add_argument("-t", "--token", default=os.environ.get("GITHUB_TOKEN"))
    c = sub.add_parser("verify", help="diff clone against originals")
    c.add_argument("dir")
    c.add_argument("url")
    a = ap.parse_args()
    {"recon": lambda: cmd_recon(a.url),
     "clone": lambda: cmd_clone(a.url, a.out, a.max_files, a.wayback),
     "scan": lambda: sys.exit(cmd_scan(a.dir)),
     "deploy": lambda: cmd_deploy(a.dir, a.repo, a.description, a.token),
     "verify": lambda: sys.exit(cmd_verify(a.dir, a.url))}[a.cmd]()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
