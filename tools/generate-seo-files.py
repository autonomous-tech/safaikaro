#!/usr/bin/env python3
"""
generate-seo-files.py — single generator for sitemap.xml, llms.txt, llms-full.txt.

Why this exists: those three files used to be hand-maintained and drifted out
of sync with the actual site (stale lastmod dates, missing pages/blog posts,
a 404ing llms-full.txt, prices that could silently diverge from prices.js).
This script derives all three deterministically from the repo itself, so
"the site" is always the single source of truth.

Usage:
    python3 tools/generate-seo-files.py

Design notes:
- stdlib only (html.parser, re, subprocess, pathlib) — no pip install needed
  in CI or locally.
- Redirect stub pages (the old dha-phase-*/clifton-block-* URLs, ~400 bytes,
  <meta http-equiv="refresh"> pointing at a hub page) are detected by the
  presence of that meta-refresh tag, not by a hardcoded filename list — if a
  new stub is ever added the same way, it's picked up automatically.
- lastmod comes from `git log -1 --format=%cs -- <file>` (last commit that
  touched the file), falling back to the file's mtime if it isn't tracked in
  git (e.g. mid-edit, uncommitted).
- Page/blog ordering is a fixed list for readability + determinism; anything
  new that isn't in the list yet is appended in sorted order, so the script
  never needs to be told about a page by name to include it.
- Service area list is the single source of truth for JOB 1's expansion —
  reused here for llms.txt's Service Areas section instead of being retyped.
- Running this script twice with no repo changes must produce byte-identical
  output (idempotent) — see the run-twice check in the task's verification
  step.
"""

from __future__ import annotations

import re
import subprocess
import sys
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://safaikaro.pk"

# Directories to never walk into when looking for *.html pages.
EXCLUDE_DIRS = {".git", ".github", ".agents", ".entire", "tools", "images"}

# Files that are never real pages even though they end in .html.
EXCLUDE_FILES = {"404.html"}

# ---------------------------------------------------------------------------
# Single source of truth: service areas (mirrors the JOB 1 expansion in
# index.html's LocalBusiness JSON-LD). Keep DHA + Clifton first — they are
# the flagship, granular coverage; everything else is the citywide expansion.
# ---------------------------------------------------------------------------
DHA_PHASES = ["Phase 1", "Phase 2", "Phase 4", "Phase 5", "Phase 6", "Phase 7", "Phase 7 Extension", "Phase 8"]
CLIFTON_BLOCKS = ["Block 1", "Block 2", "Block 3", "Block 4", "Block 5", "Block 6", "Block 7", "Block 8", "Block 9"]
OTHER_FLAGSHIP_AREAS = ["Bath Island", "PECHS"]
CITYWIDE_EXPANSION_AREAS = [
    "North Nazimabad", "Federal B. Area", "Gulshan-e-Iqbal", "Nazimabad", "Buffer Zone",
    "Gulberg", "Liaquatabad", "Bahadurabad", "Dhoraji Colony", "Mohammad Ali Society",
    "Karsaz", "Tariq Road", "Garden East", "Garden West", "Scheme 33",
    "Gulshan-e-Maymar", "Saadi Town", "Malir Cantt", "Model Colony", "North Karachi",
    "Saddar", "Soldier Bazaar", "Civil Lines", "Shah Faisal Colony",
    "Korangi Industrial Area", "S.I.T.E. Area", "Korangi Town", "Landhi", "Port Qasim",
]

# ---------------------------------------------------------------------------
# Deterministic ordering + sitemap priority/changefreq conventions.
# Anything discovered on disk that isn't listed here is appended afterwards
# in sorted order, so new pages are never silently dropped.
# ---------------------------------------------------------------------------
PAGE_ORDER = [
    "/",
    "/book",
    "/pest-control-price-list-karachi",
    "/termite-treatment-new-construction-karachi",
    "/fumigation-services-karachi",
    "/annual-pest-control-karachi",
    "/mosquito-dengue-control-karachi",
    "/cockroach-control-karachi",
    "/rodent-control-karachi",
    "/bed-bug-treatment-karachi",
    "/bee-wasp-removal-karachi",
    "/ant-control-karachi",
    "/lizard-control-karachi",
    "/fumigation-certificate-karachi",
    "/school-fumigation-service-karachi",
    "/pest-control-dha-karachi",
    "/pest-control-clifton-karachi",
    "/pest-control-karachi-areas",
    "/commercial",
    "/blog/",
]

# Top-traffic post first (khatmal), then the rest in a stable, readable order.
BLOG_ORDER = [
    "/blog/khatmal-ka-ilaj-karachi",
    "/blog/deemak-ka-ilaj-karachi",
    "/blog/fumigation-kya-hoti-hai",
    "/blog/termite-proofing-new-construction-karachi",
    "/blog/dengue-se-bachao-karachi",
    "/blog/fumigation-machine-price-pakistan",
    "/blog/fumigation-vs-pest-control-farq",
    "/blog/fumigation-bachon-pets-ke-liye-safe",
    "/blog/ghar-ko-fumigation-ke-liye-tayar-karna",
    "/blog/chipkali-bhagane-ka-tarika",
    "/blog/cockroach-killer-spray-karachi",
]

# path -> (priority, changefreq). Falls back to DEFAULT_PRIORITY below.
PRIORITY_MAP = {
    "/": ("1.0", "weekly"),
    "/book": ("0.9", "monthly"),
    "/pest-control-price-list-karachi": ("0.9", "monthly"),
    "/termite-treatment-new-construction-karachi": ("0.9", "monthly"),
    "/pest-control-dha-karachi": ("0.9", "monthly"),
    "/pest-control-clifton-karachi": ("0.9", "monthly"),
    "/pest-control-karachi-areas": ("0.8", "monthly"),
    "/fumigation-services-karachi": ("0.8", "monthly"),
    "/annual-pest-control-karachi": ("0.8", "monthly"),
    "/fumigation-certificate-karachi": ("0.8", "monthly"),
    "/mosquito-dengue-control-karachi": ("0.8", "monthly"),
    "/cockroach-control-karachi": ("0.8", "monthly"),
    "/rodent-control-karachi": ("0.8", "monthly"),
    "/bed-bug-treatment-karachi": ("0.8", "monthly"),
    "/school-fumigation-service-karachi": ("0.8", "monthly"),
    "/commercial": ("0.7", "monthly"),
    "/bee-wasp-removal-karachi": ("0.7", "monthly"),
    "/ant-control-karachi": ("0.7", "monthly"),
    "/lizard-control-karachi": ("0.7", "monthly"),
    "/blog/": ("0.6", "monthly"),
}
DEFAULT_BLOG_PRIORITY = ("0.7", "monthly")
# Area pages are discovered by URL shape, never listed by name: the citywide
# expansion adds districts faster than anyone edits this file. Hubs (DHA,
# Clifton, the areas index) are in PAGE_ORDER/PRIORITY_MAP above.
AREA_PATTERN = re.compile(r"^/pest-control-[a-z0-9-]+-karachi$|^/pest-control-north-karachi$")
AREA_HUB = "/pest-control-karachi-areas"
AREA_PRIORITY = ("0.7", "monthly")
DEFAULT_PRIORITY = ("0.6", "monthly")

EM_DASH = "—"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------
def find_html_files() -> list[Path]:
    out = []
    for p in ROOT.rglob("*.html"):
        rel = p.relative_to(ROOT)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if p.name in EXCLUDE_FILES:
            continue
        out.append(p)
    return sorted(out)


def url_path_for(rel_path: Path) -> str:
    """Map a repo-relative file path to the clean URL used across the site."""
    parts = rel_path.with_suffix("").parts  # drop .html
    if parts == ("index",):
        return "/"
    if parts[-1] == "index":
        return "/" + "/".join(parts[:-1]) + "/"
    return "/" + "/".join(parts)


def is_stub(html_text: str) -> bool:
    return bool(re.search(r'<meta\s+http-equiv=["\']refresh["\']', html_text, re.I))


def extract_title(html_text: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html_text, re.S | re.I)
    title = unescape(m.group(1)).strip() if m else ""
    return title.replace(EM_DASH, " -")


def git_lastmod(path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", str(path)],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
        date = result.stdout.strip()
        if date:
            return date
    except Exception:
        pass
    # Fallback: file mtime (uncommitted file, or git unavailable).
    import datetime
    return datetime.date.fromtimestamp(path.stat().st_mtime).isoformat()


def order_key(order_list, path):
    try:
        return (0, order_list.index(path))
    except ValueError:
        return (1, path)


# ---------------------------------------------------------------------------
# Price table (parsed from prices.js — never hand-copied, so it can't drift)
# ---------------------------------------------------------------------------
CATEGORIES = [
    ("General fumigation", "fumigation", ["s", "m", "ml", "l", "xl"], ""),
    ("Termite treatment (post-construction, 5-year warranty)", "termite", ["s", "m", "ml", "l", "xl"], ""),
    ("Bed bug treatment (both sessions included)", "bedbug", ["s", "m", "ml", "l", "xl"], ""),
    ("Rodent control (2 visits included)", "rodent", ["s", "m", "ml", "l", "xl"], ""),
    ("Mosquito control", "mosquito", ["s", "m", "ml", "l", "xl"], ""),
    ("Annual Shield (4 visits + 1 emergency callout)", "annual", ["s", "m", "ml", "l", "xl"], "/yr"),
]
TIER_HEADERS = ["Up to 100", "101-200", "201-300", "301-500", "501-1,000"]


def parse_prices_js(text: str) -> dict[str, int]:
    prices = {}
    for m in re.finditer(r"'([a-z0-9-]+)':\s*(\d+)", text):
        prices[m.group(1)] = int(m.group(2))
    return prices


def fmt_price(amount: int) -> str:
    return f"Rs {amount:,}"


def build_price_table(prices: dict[str, int]) -> str:
    header = "| Service | " + " | ".join(TIER_HEADERS) + " |"
    sep = "|---" * (len(TIER_HEADERS) + 1) + "|"
    rows = [header, sep]
    for label, prefix, tiers, suffix in CATEGORIES:
        cells = []
        for tier in tiers:
            key = f"{prefix}-{tier}"
            if key in prices:
                cells.append(fmt_price(prices[key]) + suffix)
            else:
                cells.append("n/a")
        rows.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# llms-full.txt: strip tags/scripts/styles, keep headings as markdown
# ---------------------------------------------------------------------------
SKIP_TAGS = {"script", "style", "nav", "footer", "head"}
BLOCK_TAGS = {
    "p", "div", "section", "li", "ul", "ol", "br", "tr", "table", "article",
    "h1", "h2", "h3", "h4", "h5", "h6", "header", "main", "button",
}
HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}


class MainTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_stack: list[str] = []
        self.heading_level = None
        self.heading_buf: list[str] = []
        self.out: list[str] = []

    def _skipping(self) -> bool:
        return bool(self.skip_stack)

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip_stack.append(tag)
            return
        if self._skipping():
            return
        if tag in HEADING_TAGS:
            self.heading_level = HEADING_TAGS[tag]
            self.heading_buf = []
        elif tag in BLOCK_TAGS:
            self.out.append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag not in SKIP_TAGS and not self._skipping() and tag in BLOCK_TAGS:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            if self.skip_stack and self.skip_stack[-1] == tag:
                self.skip_stack.pop()
            elif tag in self.skip_stack:
                self.skip_stack.remove(tag)
            return
        if self._skipping():
            return
        if tag in HEADING_TAGS and self.heading_level is not None:
            text = "".join(self.heading_buf).strip()
            if text:
                self.out.append("\n" + "#" * self.heading_level + " " + text + "\n")
            self.heading_level = None
            self.heading_buf = []
        elif tag in BLOCK_TAGS:
            self.out.append("\n")

    def handle_data(self, data):
        if self._skipping():
            return
        if self.heading_level is not None:
            self.heading_buf.append(data)
        else:
            self.out.append(data)

    def get_text(self) -> str:
        raw = "".join(self.out)
        # Collapse runs of whitespace within lines, but keep line breaks.
        lines = []
        for line in raw.split("\n"):
            collapsed = re.sub(r"[ \t]+", " ", line).strip()
            lines.append(collapsed)
        text = "\n".join(lines)
        # Collapse 3+ blank lines down to 1 blank line.
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def extract_main_text(html_text: str) -> str:
    parser = MainTextExtractor()
    parser.feed(html_text)
    parser.close()
    return parser.get_text().replace(EM_DASH, " - ")


# ---------------------------------------------------------------------------
# Page collection
# ---------------------------------------------------------------------------
class Page:
    def __init__(self, path: Path, url: str, title: str, lastmod: str, html_text: str):
        self.path = path
        self.url = url
        self.title = title
        self.lastmod = lastmod
        self.html_text = html_text


def collect_pages() -> list[Page]:
    pages = []
    for path in find_html_files():
        text = path.read_text(encoding="utf-8")
        if is_stub(text):
            continue
        rel = path.relative_to(ROOT)
        url = url_path_for(rel)
        title = extract_title(text)
        lastmod = git_lastmod(path)
        pages.append(Page(path, url, title, lastmod, text))
    return pages


# ---------------------------------------------------------------------------
# sitemap.xml
# ---------------------------------------------------------------------------
def priority_for(url: str) -> tuple[str, str]:
    if url in PRIORITY_MAP:
        return PRIORITY_MAP[url]
    if url.startswith("/blog/") and url != "/blog/":
        return DEFAULT_BLOG_PRIORITY
    if is_area_page(url):
        return AREA_PRIORITY
    return DEFAULT_PRIORITY


def is_area_page(url: str) -> bool:
    return bool(AREA_PATTERN.match(url)) and url not in PRIORITY_MAP


def build_sitemap(pages: list[Page]) -> str:
    by_url = {p.url: p for p in pages}

    core_urls = [u for u in PAGE_ORDER if u in by_url]
    blog_urls = [u for u in BLOG_ORDER if u in by_url]
    area_urls = sorted(u for u in by_url if is_area_page(u))
    known = set(core_urls) | set(blog_urls) | set(area_urls)
    extra_urls = sorted(u for u in by_url if u not in known)

    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">', ""]

    def emit_group(comment: str, urls: list[str]):
        if not urls:
            return
        lines.append(f"  <!-- {comment} -->")
        for u in urls:
            p = by_url[u]
            priority, changefreq = priority_for(u)
            loc = BASE_URL + u if u != "/" else BASE_URL + "/"
            lines.append("  <url>")
            lines.append(f"    <loc>{loc}</loc>")
            lines.append(f"    <lastmod>{p.lastmod}</lastmod>")
            lines.append(f"    <changefreq>{changefreq}</changefreq>")
            lines.append(f"    <priority>{priority}</priority>")
            lines.append("  </url>")
        lines.append("")

    emit_group("Core pages", core_urls)
    emit_group("Area pages", area_urls)
    emit_group("Blog posts", blog_urls)
    emit_group("Additional pages", extra_urls)

    if lines[-1] == "":
        lines.pop()
    lines.append("")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# llms.txt
# ---------------------------------------------------------------------------
def build_service_areas_md() -> str:
    lines = [
        "- **DHA Karachi:** " + ", ".join(DHA_PHASES),
        "- **Clifton:** " + ", ".join(CLIFTON_BLOCKS),
        "- **Other flagship areas:** " + ", ".join(OTHER_FLAGSHIP_AREAS),
        "- **Citywide expansion:** " + ", ".join(CITYWIDE_EXPANSION_AREAS),
    ]
    return "\n".join(lines)


def build_pages_md(pages: list[Page]) -> str:
    by_url = {p.url: p for p in pages if not p.url.startswith("/blog/") or p.url == "/blog/"}
    ordered = [u for u in PAGE_ORDER if u in by_url]
    extra = sorted(u for u in by_url if u not in ordered)
    lines = []
    for u in ordered + extra:
        p = by_url[u]
        lines.append(f"- [{p.title}]({BASE_URL}{u})")
    return "\n".join(lines)


def build_blog_md(pages: list[Page]) -> str:
    by_url = {p.url: p for p in pages if p.url.startswith("/blog/") and p.url != "/blog/"}
    ordered = [u for u in BLOG_ORDER if u in by_url]
    extra = sorted(u for u in by_url if u not in ordered)
    lines = []
    for u in ordered + extra:
        p = by_url[u]
        lines.append(f"- [{p.title}]({BASE_URL}{u})")
    return "\n".join(lines)


def build_llms_txt(pages: list[Page], prices: dict[str, int]) -> str:
    template = (ROOT / "tools" / "llms-narrative-template.md").read_text(encoding="utf-8")
    content = template
    content = content.replace("{{PRICE_TABLE}}", build_price_table(prices))
    content = content.replace("{{SERVICE_AREAS}}", build_service_areas_md())
    content = content.replace("{{PAGES}}", build_pages_md(pages))
    content = content.replace("{{BLOG_POSTS}}", build_blog_md(pages))
    content = content.replace(EM_DASH, " - ")
    if not content.endswith("\n"):
        content += "\n"
    return content


# ---------------------------------------------------------------------------
# llms-full.txt
# ---------------------------------------------------------------------------
def build_llms_full_txt(pages: list[Page]) -> str:
    by_url = {p.url: p for p in pages}
    ordered_main = [u for u in PAGE_ORDER if u in by_url and u != "/blog/"]
    ordered_blog = [u for u in BLOG_ORDER if u in by_url]
    known = set(ordered_main) | set(ordered_blog) | ({"/blog/"} if "/blog/" in by_url else set())
    extra = sorted(u for u in by_url if u not in known)

    order = ordered_main[:]
    if "/blog/" in by_url:
        order.append("/blog/")
    order += ordered_blog + extra

    parts = []
    for u in order:
        p = by_url[u]
        body = extract_main_text(p.html_text)
        parts.append(f"URL: {BASE_URL}{u}\nTITLE: {p.title}\n\n{body}\n")
    return ("\n---\n\n".join(parts)).strip() + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def write_if_changed(path: Path, content: str) -> str:
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old == content:
        return "unchanged"
    path.write_text(content, encoding="utf-8")
    return "created" if old is None else "updated"


def main() -> int:
    pages = collect_pages()
    prices = parse_prices_js((ROOT / "prices.js").read_text(encoding="utf-8"))

    sitemap = build_sitemap(pages)
    llms_txt = build_llms_txt(pages, prices)
    llms_full = build_llms_full_txt(pages)

    results = {
        "sitemap.xml": write_if_changed(ROOT / "sitemap.xml", sitemap),
        "llms.txt": write_if_changed(ROOT / "llms.txt", llms_txt),
        "llms-full.txt": write_if_changed(ROOT / "llms-full.txt", llms_full),
    }

    non_stub_count = len(pages)
    blog_count = len([p for p in pages if p.url.startswith("/blog/") and p.url != "/blog/"])
    print(f"Scanned {non_stub_count} non-stub pages ({blog_count} blog posts).")
    for name, status in results.items():
        print(f"  {name}: {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
