# SafaiKaro Website — Developer Guide

SafaiKaro is a pest control service targeting DHA and Clifton areas of Karachi, Pakistan. The website is built as static HTML/CSS with no build step — open any `.html` file in a browser.

## Folder Structure

```
safaikaro/
├── pages/                                        ← All HTML files
│   ├── index.html                                ← Homepage
│   ├── book.html                                 ← Booking wizard
│   ├── styles.css                                ← Shared stylesheet
│   ├── pest-control-dha-karachi.html             ← DHA area hub
│   ├── pest-control-dha-phase-5-karachi.html     ← DHA Phase 5
│   ├── pest-control-dha-phase-6-karachi.html     ← DHA Phase 6
│   ├── pest-control-dha-phase-7-karachi.html     ← DHA Phase 7
│   ├── pest-control-dha-phase-8-karachi.html     ← DHA Phase 8
│   ├── pest-control-clifton-karachi.html         ← Clifton area hub
│   ├── pest-control-clifton-block-4-karachi.html ← Clifton Block 4
│   ├── pest-control-clifton-block-5-karachi.html ← Clifton Block 5
│   ├── pest-control-clifton-block-7-karachi.html ← Clifton Block 7
│   ├── pest-control-clifton-block-9-karachi.html ← Clifton Block 9
│   ├── pest-control-price-list-karachi.html      ← Full pricing page
│   ├── annual-pest-control-karachi.html          ← Annual plan page
│   ├── termite-treatment-new-construction-karachi.html ← Termite service
│   ├── commercial.html                           ← Commercial/B2B page
│   └── shared-context.md                         ← Build context (not deployed)
├── images/                                       ← Generated and real photos
│   ├── hero-tech-dha-villa.png
│   └── ...
├── outputs/                                      ← Research outputs
├── safaikaro-spec.md                              ← SEO research and content spec
└── README.md                                     ← This file
```

## How to Update Pricing

All pricing is in `styles.css` (CSS variables) and inline in each HTML file. Search for `Rs` to find all price instances.

Pricing appears in:
- `index.html` — service cards
- `pest-control-price-list-karachi.html` — full pricing table
- All DHA Phase and Clifton Block area pages — local pricing sections
- `annual-pest-control-karachi.html` — annual plan pricing
- `termite-treatment-new-construction-karachi.html` — termite pricing
- `commercial.html` — monthly contract starting price

## How to Add a New Area Page

1. Copy `pest-control-dha-phase-5-karachi.html` as a template
2. Replace all phase-5 references with new area name
3. Update SEO title, meta description, H1
4. Update breadcrumb schema
5. Add internal link from parent area page (DHA or Clifton page)
6. Add to footer navigation if prominent enough

## How to Replace Placeholder Phone Numbers

Search for `+92-XXX-XXXXXXX` across all files — replace with real number.

Search for `wa.me/923000000000` — replace `923000000000` with real WhatsApp number in international format (e.g., `923001234567`).

## How to Replace Images

- All images in `/images/` folder
- Referenced in HTML as `../images/filename.png` (from pages/) or `images/filename.png` (from root)
- Replace AI-generated placeholders with real photos
- Maintain same filenames or do a find-replace across all HTML files

## Live Preview

Open any `.html` file in a browser. All styles are in `styles.css` (shared).

No build step required — pure static HTML/CSS/JS.

## Deployment

Upload `/pages/` and `/images/` folders to any web host or CDN.

**Cloudflare Pages:**
1. Connect GitHub repo
2. Deploy from `/pages/` as root
3. Custom domain: `safaikaro.pk` → point to hosting + add SSL

**Any static host (Netlify, Vercel, etc.):**
1. Set `/pages/` as publish directory
2. No build command needed

## Design System

- **Fonts:** Sora (headings), DM Sans (body) — via Google Fonts
- **Primary:** `#0D4A2F` (deep forest green)
- **Accent:** `#6EE086` (bright lime) — CTA buttons
- **Background:** `#F9F8F4` (off-white)
- **Style:** Energetic design system — thick 4px borders, bold typography, snappy hover animations
- **CSS variables** defined in `:root` in `styles.css`
