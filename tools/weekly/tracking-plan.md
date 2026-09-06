---
type: spec
status: DONE (code items shipped c4251bf 2026-09-06; founder items open)
client: safaikaro
created: 2026-09-06
---

# SafaiKaro — event tracking plan for CRO reporting (2026-09-06)

Source: repo grep of all 49 pages + PostHog 28d event mix (project 353082, test IDs excluded). Companion data: `scratch/safaikaro-cro-check-2026-09-06/`.

## What exists today

| Layer | State |
|---|---|
| PostHog init | 43 of 49 pages (`defaults:'2026-01-30'` = autocapture, pageleave, scroll depth on). Missing on 17 district pages + restaurant redirect stub. |
| Lead events | `whatsapp_click` / `book_click` / `call_click` via one delegated listener in `prices.js` (props: path, text, href). Fires nowhere `prices.js` isn't loaded. |
| Funnel events | `booking_*` chain (5), `pricing_selection_change`, `pricing_quote_click`, `khatmal_*` (3), `commercial_survey_request`, `wa_desktop_card_open`, `phone_copy`. |
| Attribution | Referrer only. Zero UTM on any inbound link. Direct = 25% of visitors, 22% of leads, origin unknown. |
| Lead quality | None. `whatsapp_click` is intent; no join to conversation, quote or job. |

28d mix: 450 pageviews, 55 whatsapp_click (38 persons), 12 book_click, 1 call_click, 485 autocapture (noise).

## NOW (in impact order)

### 1. ~~Instrument the 17 district pages~~ CORRECTED: they are redirect stubs
- The 17 `clifton-block-*` / `dha-phase-*` files are ~400-byte meta-refresh stubs for legacy URLs, excluded from the sitemap by design. Nothing to instrument. Initial finding was wrong.
- Real gap found by the new check: `blog/index.html` never loaded `prices.js`, so its 6 CTAs were untracked. **Fixed.**
- Clifton hub linked its 9 block sections through the stubs; now links `#block-N` directly. **Fixed.**
- `tools/check-tracking.py` (CI, before regen) fails on any real page without PostHog + prices.js, or any internal link to a stub.

### 2. Add a `cta` placement property to every lead event — SHIPPED
- 19 of 55 WA clicks (35%) carry empty `text` (icon-only float pill). Hero vs sticky bar vs float vs inline vs footer vs price row is not separable, so the audit's "remove duplicate overlays" test cannot be read.
- Shipped without touching page markup: placement derived from the DOM at click time in the `prices.js` delegate (`hero|nav|sticky|float|footer|faq|price-row|desktop-card|article|inline`), plus `section` (nearest section id/H2) and decoded `prefill`. `data-cta` on any ancestor overrides. Playwright-verified on / and /rodent-control-karachi: 11/11 anchors fire, 0 empty text.
- Report: `cta_placement_*` + `landing_*` queries in `scratch/safaikaro-cro-check-2026-09-06/pull.py`. Data from 2026-09-06 onward only; older clicks show as `(pre-tag)`.

### 3. UTM the owned inbound links
- GBP website link → `?utm_source=gbp&utm_medium=organic`; GBP posts → `utm_source=gbp_post`; WhatsApp-shared/broadcast links → `utm_source=whatsapp`; invoice/quotation footer → `utm_source=invoice`.
- PostHog stores UTMs automatically; the pull script's source bucket then splits "direct" into GBP / WhatsApp / true direct. This is the only way to see GBP's lead share on-site (calls stay invisible; use GBP Insights for those).
- ~15 min. Founder does the GBP edit.

### 4. Close the lead-quality loop — REVERTED 00fe52f (founder: customers must not send a code)
- `ref` = `{page}/{placement}` is on the `whatsapp_click` event only; the wa.me message is never modified. The click→job join is manual: SDR records page (from what the customer says or the prefill wording, which already names service/area on 40 pages) and outcome in the district-jobs scoreboard. Alternative if the manual join proves too lossy: a per-page WhatsApp *number* or a Business API inbox, both outside the site.
- Monthly join: `whatsapp_click` by cta/page → jobs. Turns CRO reporting from click rate into Rs per landing page. Founder rejected the visible tag 2026-09-06 after seeing it in the outgoing message.

### 5. Micro-conversions on high-attention pages — SHIPPED (faq_open, price_tab_change, nav_menu_open; fire on open only)
Only where they change a decision:
- `faq_open {question, path}` — 158 FAQ items sitewide, zero signal on which objections people open before/instead of converting. One line in the shared FAQ handler.
- `price_tab_change {service}` on the homepage tabs (price-list tabs already tracked; homepage isn't).
- `nav_menu_open` on mobile — tells whether the hamburger competes with the sticky bar.
- Generic `content_cta_click {page, variant}` and `content_symptom_selected {page, symptom}` for future blogs instead of new `khatmal_*` names per post.
- ~1 h.

## LATER
- `call_click`: RESOLVED as a CRO fact, not a tracking bug. The mobile sticky bar has WhatsApp + Book only; the sole `tel:` link is the desktop nav phone. Mobile visitors are never offered a call. Test adding a call button to the sticky bar (mobile = 81% of visitors).
- DONE: `pull.py` now reports lead persons by landing page via the `sessions` table (28d: home 10/54, rodent 8/23, khatmal blog 7/84, bee-wasp 7/16).
- Fix the zero-duration bounce artifact in the session query (board item) before quoting bounce rate.
- Scroll depth already exists (`$prev_pageview_max_scroll_percentage`; home 40%, khatmal 48%, price list 46%). Report it per page; no new event needed.
- Turn autocapture off or restrict to `[data-cta]` once item 2 ships; it is 485 of ~1,400 events and adds nothing the named events don't.
- Session replay: recording flag present on 119 pageviews but only 2 `$snapshot` events; check replay sampling/quota in project settings before relying on replays for CRO review.

## Primary metric (unchanged from 2026-09-01 audit)
Unique lead persons / unique visitors, by device × landing page × `cta`. Secondary: booking-chain completion, quoted and booked jobs per landing page (item 4).

## Sitemap changes shipped (c4251bf)
- Area pages discovered by URL shape (`/pest-control-*-karachi`), emitted as an "Area pages" group at 0.7; areas hub explicit at 0.8. Previously 13 pages sat alphabetically in "Additional pages" at 0.6. Future districts classify themselves.
- chipkali + cockroach posts added to blog order; restaurant stub dropped from page lists. Generator idempotent, 43 URLs.
- Not done, deliberately: image sitemap (no job photos yet), hreflang (single-language URLs), priority games (Google ignores priority/changefreq; completeness + lastmod are what matter).
