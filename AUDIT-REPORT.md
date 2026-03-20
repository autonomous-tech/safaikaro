# SafaiKaro Website — Sanity Audit Report

**Date:** 2026-03-20
**Auditor:** Claude Code
**Scope:** All 19 HTML pages in `/pages/`

---

## 1. File Inventory

19 HTML files found:

| # | File | Status |
|---|------|--------|
| 1 | index.html | exists |
| 2 | book.html | exists |
| 3 | commercial.html | exists |
| 4 | annual-pest-control-karachi.html | exists |
| 5 | pest-control-price-list-karachi.html | exists |
| 6 | termite-treatment-new-construction-karachi.html | exists |
| 7 | pest-control-dha-karachi.html | exists |
| 8 | pest-control-dha-phase-1-karachi.html | exists (untracked) |
| 9 | pest-control-dha-phase-2-karachi.html | exists (untracked) |
| 10 | pest-control-dha-phase-4-karachi.html | exists (untracked) |
| 11 | pest-control-dha-phase-5-karachi.html | exists |
| 12 | pest-control-dha-phase-6-karachi.html | exists |
| 13 | pest-control-dha-phase-7-karachi.html | exists |
| 14 | pest-control-dha-phase-8-karachi.html | exists |
| 15 | pest-control-clifton-karachi.html | exists |
| 16 | pest-control-clifton-block-1-karachi.html | exists |
| 17 | pest-control-clifton-block-4-karachi.html | exists |
| 18 | pest-control-clifton-block-5-karachi.html | exists |
| 19 | pest-control-clifton-block-7-karachi.html | exists |
| 20 | pest-control-clifton-block-9-karachi.html | exists |

**Note:** DHA Phase 3 intentionally removed (commit c7a8ee2). No links reference it.

---

## 2. Link Audit — All Pages

Every internal `href="*.html"` across all 19 pages was checked against existing files.

### Broken Links

| Source File | Broken Target | Fix |
|-------------|--------------|-----|
| pest-control-clifton-karachi.html:64 | pest-control-clifton-block-2-karachi.html | Create file or remove link |
| pest-control-clifton-karachi.html:67 | pest-control-clifton-block-3-karachi.html | Create file or remove link |
| pest-control-clifton-karachi.html:76 | pest-control-clifton-block-6-karachi.html | Create file or remove link |
| pest-control-clifton-karachi.html:82 | pest-control-clifton-block-8-karachi.html | Create file or remove link |

All other internal links resolve correctly.

- **Total links checked:** ~200+
- **Broken:** 4

---

## 3. DHA Page Links Check (`pest-control-dha-karachi.html`)

### Phases Grid Section (lines 82-89)

> **FAIL:** The "Phases Grid" section has a heading "DHA Phase 1 to Phase 8 — Fully Covered" and text "Click any phase to see local pest control details" but **contains zero phase links**. The grid is completely empty.

### "Explore DHA Phase Pages" Section (lines 243-248)

| Link | Target | Status |
|------|--------|--------|
| Phase 5 | pest-control-dha-phase-5-karachi.html | exists |
| Phase 6 | pest-control-dha-phase-6-karachi.html | exists |
| Phase 7 | pest-control-dha-phase-7-karachi.html | exists |
| Phase 8 | pest-control-dha-phase-8-karachi.html | exists |

> **FAIL:** Phase 1, 2, and 4 pages now exist but are NOT linked from the DHA landing page. They should be added to both the phases grid and the explore section.

---

## 4. Clifton Page Links Check (`pest-control-clifton-karachi.html`)

All 9 blocks are listed in the Blocks Grid (lines 60-88):

| Link | Target | Status |
|------|--------|--------|
| Block 1 | pest-control-clifton-block-1-karachi.html | exists |
| Block 2 | pest-control-clifton-block-2-karachi.html | **MISSING** |
| Block 3 | pest-control-clifton-block-3-karachi.html | **MISSING** |
| Block 4 | pest-control-clifton-block-4-karachi.html | exists |
| Block 5 | pest-control-clifton-block-5-karachi.html | exists |
| Block 6 | pest-control-clifton-block-6-karachi.html | **MISSING** |
| Block 7 | pest-control-clifton-block-7-karachi.html | exists |
| Block 8 | pest-control-clifton-block-8-karachi.html | **MISSING** |
| Block 9 | pest-control-clifton-block-9-karachi.html | exists |

> **FAIL:** 4 Clifton block pages are missing: Block 2, 3, 6, 8. Create them or remove their links.

---

## 5. CSS Class Audit (Spot Check — 3 Pages)

### index.html

| Check | Result |
|-------|--------|
| No `var(--)` references | PASS |
| No BEM `__` in nav/footer | PASS |
| `<table class="pricing-table">` | PASS (line 191) |
| FAQ uses `faq-q` / `faq-a` | PASS |
| FAQ accordion JS present | PASS |

### pest-control-price-list-karachi.html

| Check | Result |
|-------|--------|
| No `var(--)` references | PASS |
| No BEM `__` in nav/footer | PASS |
| `<table class="pricing-table">` | PASS (line 103) |
| FAQ uses `faq-q` / `faq-a` | PASS |
| FAQ chevron | WARN — uses `<span>&#8964;</span>` text char, not SVG (inconsistent but functional) |

### termite-treatment-new-construction-karachi.html

| Check | Result |
|-------|--------|
| No `var(--)` references | PASS |
| No BEM `__` in nav/footer | PASS |
| Comparison table `class="pricing-table"` | **FAIL** — line 217: `<table>` has no class. Should add `class="pricing-table"` |
| FAQ uses `faq-q` / `faq-a` | PASS |

### CSS file (styles.css)

| Check | Result |
|-------|--------|
| `var(--shadow)` at line 1321 | PASS — `--shadow` defined at line 53 |

---

## 6. Nav Audit (5 Pages)

Checked: index.html, pest-control-price-list-karachi.html, pest-control-dha-karachi.html, pest-control-clifton-karachi.html, commercial.html

| Check | index | price-list | dha | clifton | commercial |
|-------|-------|-----------|-----|---------|------------|
| `id="navbar"` on `<nav>` | PASS | PASS | PASS | PASS | PASS |
| `id="navLinks"` on nav-links div | PASS | PASS | PASS | PASS | PASS |
| onclick hamburger handler | PASS | PASS | PASS | PASS | PASS |
| Book Now `btn-lime` link | PASS | PASS | PASS | PASS | PASS |
| `.nav-links.open` inline style | PASS | PASS | PASS | PASS | PASS |

---

## 7. Additional Issues Found

### JS Bug: `getElementById('nav')` (should be `'navbar'`)

4 pages have an old scroll-shadow script referencing `getElementById('nav')` when the nav has `id="navbar"`. This throws a console error on every scroll event.

| File | Line | Fix |
|------|------|-----|
| pest-control-price-list-karachi.html | 423 | Change `'nav'` to `'navbar'` |
| termite-treatment-new-construction-karachi.html | 538 | Change `'nav'` to `'navbar'` |
| commercial.html | 452 | Change `'nav'` to `'navbar'` |
| annual-pest-control-karachi.html | 327 | Change `'nav'` to `'navbar'` |

**Note:** These pages also have a corrected duplicate script (from the share button component block) that references `'navbar'` correctly. The old broken script should be removed.

### Duplicate scroll-shadow scripts

The same 4 pages above have **two** scroll-shadow listeners: the old broken one (`getElementById('nav')`) and a newer correct one (`getElementById('navbar')`) injected with the share component. The old script should be deleted.

### DHA Phases Grid Empty

`pest-control-dha-karachi.html` lines 82-89: The "Phases Grid" section promises clickable phase links but the grid content is completely empty. Needs phase cards linking to all 7 phase pages (1, 2, 4, 5, 6, 7, 8).

---

## Summary

| Category | Pass | Fail |
|----------|------|------|
| File inventory | 1 | 0 |
| Link audit (broken links) | 0 | 4 |
| DHA page links | 1 | 2 |
| Clifton page links | 5 | 4 |
| CSS class audit (index.html) | 4 | 0 |
| CSS class audit (price-list) | 4 | 0 |
| CSS class audit (termite) | 3 | 1 |
| Nav audit (5 pages) | 5 | 0 |
| JS getElementById bug | 0 | 4 |
| Duplicate scripts | 0 | 4 |
| Empty phases grid | 0 | 1 |

### Totals: 23 passed, 20 failed

### Priority Fixes

1. **HIGH — Create 4 missing Clifton block pages** (Block 2, 3, 6, 8) or remove dead links
2. **HIGH — Populate DHA phases grid** with links to all 7 phase pages
3. **HIGH — Add Phase 1, 2, 4 links** to DHA landing page "Explore" section
4. **MED — Fix `getElementById('nav')` → `getElementById('navbar')`** on 4 pages
5. **MED — Remove duplicate scroll-shadow scripts** on 4 pages
6. **LOW — Add `class="pricing-table"`** to termite comparison table
