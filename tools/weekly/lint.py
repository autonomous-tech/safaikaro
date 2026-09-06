#!/usr/bin/env python3
"""lint.py: the PR gate. Exit 1 on any finding in changed HTML (vs origin/main) or in the ledger files.

Checks: banned phrases (config), em-dashes, literal Rs prices not present in prices.js, broken internal links,
JSON-LD parse + FAQPage parity with on-page FAQ text, new pages missing PostHog/prices.js, changed pages missing
from sitemap.xml, ledger/instrumentation entries missing required fields. Then runs tools/check-tracking.py.
Usage: python tools/weekly/lint.py [--all] [--base origin/main]
"""
import argparse, html, json, re, subprocess, sys
from pathlib import Path

from common import CONFIG, HERE, ROOT, git

SKIP = {".git", ".github", ".agents", ".entire", "tools", "images"}


def price_set():
    js = (ROOT / "prices.js").read_text(encoding="utf-8")
    return {int(x.replace(",", "")) for x in re.findall(r"\b(\d{1,3}(?:,\d{3})+|\d{4,7})\b", js)}


def page_exists(href):
    p = href.split("#")[0].split("?")[0]
    if not p.startswith("/"):
        return True
    if p in ("/", ""):
        return True
    p = p.rstrip("/")
    cands = [ROOT / (p.lstrip("/") + ".html"), ROOT / p.lstrip("/") / "index.html", ROOT / p.lstrip("/")]
    return any(c.exists() for c in cands)


def strip_tags(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s)).replace("\u2014", "-").replace("\u2013", "-")
    return re.sub(r"\s+", " ", s).strip().lower()


def added_lines(rel, base):
    """Lines this branch added to the file (legacy copy is not re-linted for em-dashes)."""
    diff = git("diff", "-U0", base, "--", rel) or git("diff", "-U0", "--", rel)
    return "\n".join(l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))


def lint_html(path, text, is_new, prices, banned, sitemap, base="origin/main"):
    rel = path.relative_to(ROOT).as_posix()
    out = []
    visible = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.S | re.I)
    # claims and em-dashes are checked on what this branch wrote (whole file for new pages, added lines otherwise);
    # `--all` passes base=None to sweep every page.
    scope = visible if (is_new or base is None) else added_lines(rel, base)
    for b in banned:
        if re.search(r"(?<!\w)" + re.escape(b) + r"(?!\w)", scope, re.I):
            out.append(f"{rel}: banned phrase '{b}'")
    if "—" in scope:
        out.append(f"{rel}: em-dash in copy you added")
    for m in re.finditer(r"Rs\.?\s?([\d,]{4,})", strip_tags(visible), re.I):
        v = int(m.group(1).replace(",", ""))
        if v not in prices:
            out.append(f"{rel}: literal price Rs {m.group(1)} not in prices.js")
    for href in set(re.findall(r'href="(/[^"]*)"', text)):
        if not page_exists(href):
            out.append(f"{rel}: broken internal link {href}")
    body_text = strip_tags(visible)
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', text, re.S):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError as e:
            out.append(f"{rel}: JSON-LD parse error {str(e)[:60]}"); continue
        nodes = data.get("@graph", [data]) if isinstance(data, dict) else data
        for node in nodes if isinstance(nodes, list) else []:
            if isinstance(node, dict) and node.get("@type") == "FAQPage":
                for q in node.get("mainEntity", []):
                    qt = strip_tags(q.get("name", ""))[:60]
                    if qt and qt not in body_text:
                        out.append(f"{rel}: FAQ schema question not on page: '{qt[:40]}'")
            if isinstance(node, dict) and "aggregateRating" in json.dumps(node):
                out.append(f"{rel}: aggregateRating in schema")
    if is_new and "posthog.init(" not in text and "http-equiv" not in text:
        out.append(f"{rel}: new page without posthog.init")
    if is_new and "prices.js" not in text and "http-equiv" not in text:
        out.append(f"{rel}: new page without prices.js")
    url = CONFIG["site_url"] + "/" + rel[:-5] if rel != "index.html" else CONFIG["site_url"] + "/"
    if sitemap and "http-equiv" not in text and rel != "404.html" and url not in sitemap and url.replace("/index", "") not in sitemap:
        out.append(f"{rel}: not in sitemap.xml (run tools/generate-seo-files.py)")
    return out


def lint_ledgers():
    out = []
    for name, req in (("ledger.json", ("id", "pages", "hypothesis", "metric")), ("instrumentation.json", ("id", "event", "question", "pages"))):
        p = HERE / name
        if not p.exists():
            continue
        try:
            entries = json.loads(p.read_text())
        except json.JSONDecodeError as e:
            out.append(f"{name}: invalid JSON {e}"); continue
        ids = [e.get("id") for e in entries]
        if len(ids) != len(set(ids)):
            out.append(f"{name}: duplicate ids")
        for e in entries:
            for k in req:
                if not e.get(k):
                    out.append(f"{name}: entry {e.get('id')} missing {k}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--base", default="origin/main")
    a = ap.parse_args()
    if a.all:
        files = [p for p in ROOT.rglob("*.html") if not (set(p.relative_to(ROOT).parts) & SKIP)]
        new = set(); a.base = None
    else:
        changed = git("diff", "--name-only", f"{a.base}...HEAD").splitlines() + git("diff", "--name-only").splitlines() + git("ls-files", "--others", "--exclude-standard").splitlines()
        files = [ROOT / f for f in dict.fromkeys(changed) if f.endswith(".html") and (ROOT / f).exists() and not (set(Path(f).parts) & SKIP)]
        new = set(git("diff", "--name-only", "--diff-filter=A", f"{a.base}...HEAD").splitlines()) | set(git("ls-files", "--others", "--exclude-standard").splitlines())
    prices, banned = price_set(), CONFIG["banned_phrases"]
    sitemap = set(re.findall(r"<loc>(.*?)</loc>", (ROOT / "sitemap.xml").read_text())) if (ROOT / "sitemap.xml").exists() else set()
    findings = []
    for p in files:
        findings += lint_html(p, p.read_text(encoding="utf-8", errors="ignore"), p.relative_to(ROOT).as_posix() in new, prices, banned, sitemap, a.base)
    findings += lint_ledgers()
    ct = ROOT / "tools/check-tracking.py"
    if ct.exists():
        r = subprocess.run([sys.executable, str(ct)], capture_output=True, text=True, cwd=ROOT)
        if r.returncode != 0:
            findings.append("check-tracking.py failed:\n" + r.stdout.strip())
    print(f"lint: {len(files)} html files checked, {len(findings)} finding(s)")
    for f in findings:
        print("  " + f)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
