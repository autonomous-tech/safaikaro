#!/usr/bin/env python3
"""check-tracking.py — fail if any real page is invisible to analytics or links to a redirect stub.

Every non-stub page must load PostHog (init snippet) and prices.js (the sitewide
delegated CTA tracker). Internal links must point at real pages, never at the
~400-byte meta-refresh stubs kept for legacy URLs. Runs in CI before the SEO
file regen; exit 1 on any finding. stdlib only.
"""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".github", ".agents", ".entire", "tools", "images"}
pages = [p for p in ROOT.rglob("*.html") if not (set(p.relative_to(ROOT).parts) & SKIP_DIRS) and p.name != "404.html"]
texts = {p: p.read_text(encoding="utf-8") for p in pages}
stubs = {p for p, t in texts.items() if re.search(r'<meta\s+http-equiv=["\']refresh["\']', t, re.I)}
stub_urls = {"/" + p.relative_to(ROOT).with_suffix("").as_posix() for p in stubs}

problems = []
for p, t in texts.items():
    if p in stubs:
        continue
    rel = p.relative_to(ROOT).as_posix()
    if "posthog.init(" not in t:
        problems.append(f"{rel}: no posthog.init")
    if "prices.js" not in t:
        problems.append(f"{rel}: prices.js not loaded (CTA clicks untracked)")
    for href in re.findall(r'href="(/[^"#?]*)', t):
        if href.rstrip("/") in stub_urls:
            problems.append(f"{rel}: links to redirect stub {href}")

real = len(pages) - len(stubs)
print(f"{real} pages checked, {len(stubs)} stubs ignored, {len(problems)} problem(s)")
for line in problems:
    print("  " + line)
sys.exit(1 if problems else 0)
